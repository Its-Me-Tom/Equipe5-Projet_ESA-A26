/*
 * can_esa.c
 *
 *  PARTIE COMMUNE — gestionnaire CAN unique de la carte (voir can_esa.h).
 *
 *  Créé pour T07 (Tom), mais il appartient à toute l'équipe : chaque tâche
 *  s'y branche aux deux « POINT DE BRANCHEMENT » au lieu de créer son
 *  propre gestionnaire. Ne pas définir HAL_CAN_RxFifo0MsgPendingCallback()
 *  ailleurs : il ne peut y en avoir qu'un.
 *
 *  Règle d'or : rien de long sous interruption. L'interruption range la
 *  trame dans une file; CanEsa_Task() (boucle principale) la distribue.
 */

#include "can_esa.h"
#include "carte_config.h"
#include "protocole_can.h"
#include "t07_eclairage.h"
#include <string.h>

/* ========================================================================= */
/* POINT DE BRANCHEMENT n° 1 : identifiants acceptés par le filtre matériel  */
/* ========================================================================= */
/* Le filtre du périphérique CAN rejette toutes les autres trames : le
 * programme ne voit que ce qui le concerne. Ajouter ici les ID d'une tâche,
 * entre #if CARTE == ... si elle n'existe que sur une carte.
 * Maximum : 56 identifiants (14 bancs de 4). */
static const uint16_t ids_acceptes[] =
{
    /* Commun */
    HEARTBEAT_RPI,

    /* T07 — DEL et éclairage (Tom) */
    ECLAIRAGE_CMD,
#if T07_A_DES_PLACES
    DEL_PLACE_CMD,
#endif

    /* Autres tâches : ajouter leurs ID ici. Exemples :
     *   ARRET_RPI, REARMEMENT_CMD, SYNCHRO_CMD        (arrêt et synchro)
     *   IR_LECTURE_CMD                                (T06, Bas et Haut)
     *   ELEVATION_CMD, ROTATION_CMD, BRAS_CMD         (T08-T10, Haut)
     */
};

/* ========================================================================= */
/* POINT DE BRANCHEMENT n° 2 : fonctions de réception des tâches             */
/* ========================================================================= */
/* Chaque trame reçue est offerte aux fonctions dans l'ordre, jusqu'à ce que
 * l'une d'elles retourne 1. */
static const CanRecepteur recepteurs[] =
{
    T07_TraiterTrameCan,        /* T07 — DEL et éclairage (Tom) */

    /* Autres tâches : ajouter leur fonction ici. */
};

/* ========================================================================= */
/* Réglages internes                                                         */
/* ========================================================================= */
#define NB_IDS_ACCEPTES     (sizeof(ids_acceptes) / sizeof(ids_acceptes[0]))
#define NB_RECEPTEURS       (sizeof(recepteurs) / sizeof(recepteurs[0]))
#define NB_BANCS_CAN1       14U     /* bancs 0 à 13 pour CAN1 */
#define TAILLE_FILE_RX      32U     /* trames reçues en attente */
#define TAILLE_FILE_TX      16U     /* trames à envoyer en attente */

/* ========================================================================= */
/* Variables                                                                 */
/* ========================================================================= */
static CAN_HandleTypeDef *can = NULL;

/* File de réception : remplie par l'interruption, vidée par CanEsa_Task() */
static CanTrame file_rx[TAILLE_FILE_RX];
static volatile uint8_t rx_tete = 0;        /* écrit par l'interruption */
static volatile uint8_t rx_queue = 0;       /* écrit par la boucle principale */
static volatile uint32_t nb_trames_perdues = 0;

/* File d'envoi : utilisée seulement par la boucle principale */
static CanTrame file_tx[TAILLE_FILE_TX];
static uint8_t tx_tete = 0;
static uint8_t tx_queue = 0;
static uint32_t nb_envois_perdus = 0;

/* Heartbeat de la carte */
static uint8_t etat_carte = HEARTBEAT_INITIALISATION;
static uint8_t compteur_heartbeat = 0;
static uint32_t dernier_heartbeat_ms = 0;

/* Surveillance du RPi */
static uint8_t rpi_deja_vu = 0;
static uint32_t dernier_heartbeat_rpi_ms = 0;

/* ========================================================================= */
/* Fonctions internes                                                        */
/* ========================================================================= */

/* Configure les filtres : une liste d'ID exacts (mode liste 16 bits,
 * 4 ID par banc), tous dirigés vers la FIFO 0. */
static HAL_StatusTypeDef ConfigurerFiltres(void)
{
    CAN_FilterTypeDef filtre = {0};

    filtre.FilterFIFOAssignment = CAN_FILTER_FIFO0;
    filtre.FilterActivation = ENABLE;
    filtre.SlaveStartFilterBank = NB_BANCS_CAN1;

#if CAN_ACCEPTER_TOUT
    /* Diagnostic : masque à 0 = tout accepter */
    filtre.FilterBank = 0;
    filtre.FilterMode = CAN_FILTERMODE_IDMASK;
    filtre.FilterScale = CAN_FILTERSCALE_32BIT;
    return HAL_CAN_ConfigFilter(can, &filtre);
#else
    filtre.FilterMode = CAN_FILTERMODE_IDLIST;
    filtre.FilterScale = CAN_FILTERSCALE_16BIT;

    for (uint32_t i = 0; i < NB_IDS_ACCEPTES; i += 4U)
    {
        uint16_t valeurs[4];

        filtre.FilterBank = i / 4U;

        if (filtre.FilterBank >= NB_BANCS_CAN1)
        {
            return HAL_ERROR;   /* trop d'ID : regrouper avec un masque */
        }

        for (uint32_t k = 0; k < 4U; k++)
        {
            /* Case libre : on répète le dernier ID de la liste */
            uint32_t index = (i + k < NB_IDS_ACCEPTES) ? (i + k) : (NB_IDS_ACCEPTES - 1U);

            /* Format 16 bits : ID standard dans les bits 15 à 5 */
            valeurs[k] = (uint16_t)(ids_acceptes[index] << 5);
        }

        filtre.FilterIdHigh = valeurs[0];
        filtre.FilterIdLow = valeurs[1];
        filtre.FilterMaskIdHigh = valeurs[2];   /* en mode liste, ce sont */
        filtre.FilterMaskIdLow = valeurs[3];    /* aussi des ID acceptés  */

        if (HAL_CAN_ConfigFilter(can, &filtre) != HAL_OK)
        {
            return HAL_ERROR;
        }
    }

    return HAL_OK;
#endif
}

/* Envoie les trames en attente tant qu'une boîte d'envoi est libre */
static void ViderFileEnvoi(void)
{
    while (tx_queue != tx_tete && HAL_CAN_GetTxMailboxesFreeLevel(can) > 0U)
    {
        CAN_TxHeaderTypeDef entete = {0};
        uint32_t boite;
        CanTrame *trame = &file_tx[tx_queue];

        entete.StdId = trame->id;
        entete.IDE = CAN_ID_STD;
        entete.RTR = CAN_RTR_DATA;
        entete.DLC = trame->dlc;
        entete.TransmitGlobalTime = DISABLE;

        if (HAL_CAN_AddTxMessage(can, &entete, trame->donnees, &boite) != HAL_OK)
        {
            break;      /* on réessaiera au prochain tour */
        }

        tx_queue = (uint8_t)((tx_queue + 1U) % TAILLE_FILE_TX);
    }
}

static void EnvoyerHeartbeat(void)
{
    uint8_t donnees[2];

    donnees[0] = compteur_heartbeat++;
    donnees[1] = etat_carte;

    CanEsa_Envoyer(CAN_ID_HEARTBEAT, donnees, 2);

#if CAN_DEL_DIAGNOSTIC
    HAL_GPIO_TogglePin(LD4_GPIO_Port, LD4_Pin);     /* vert : la carte vit */
#endif
}

/* Trames traitées par la partie commune elle-même */
static uint8_t TraiterTrameCommune(const CanTrame *trame)
{
    if (trame->id == HEARTBEAT_RPI)
    {
        rpi_deja_vu = 1;
        dernier_heartbeat_rpi_ms = HAL_GetTick();
        return 1;
    }

    return 0;
}

static void Distribuer(const CanTrame *trame)
{
    if (TraiterTrameCommune(trame))
    {
        return;
    }

    for (uint32_t i = 0; i < NB_RECEPTEURS; i++)
    {
        if (recepteurs[i](trame))
        {
            return;
        }
    }
}

/* ========================================================================= */
/* Fonctions publiques                                                       */
/* ========================================================================= */

HAL_StatusTypeDef CanEsa_Init(CAN_HandleTypeDef *hcan)
{
    can = hcan;

    /* Retransmission automatique et sortie automatique du bus-off.
     * CubeMX les a laissées à DISABLE : sans elles, une trame perdue n'est
     * jamais renvoyée et la carte reste muette après un bus-off.
     * À cocher aussi dans CubeMX (CAN1 > Parameter Settings > Basic
     * Parameters) pour que le .ioc soit à jour. */
    can->Init.AutoRetransmission = ENABLE;
    can->Init.AutoBusOff = ENABLE;

    if (HAL_CAN_Init(can) != HAL_OK)
    {
        return HAL_ERROR;
    }

    if (ConfigurerFiltres() != HAL_OK)
    {
        return HAL_ERROR;
    }

    if (HAL_CAN_Start(can) != HAL_OK)
    {
        return HAL_ERROR;
    }

    if (HAL_CAN_ActivateNotification(can, CAN_IT_RX_FIFO0_MSG_PENDING) != HAL_OK)
    {
        return HAL_ERROR;
    }

    /* Premier heartbeat tout de suite, avec l'état « initialisation » :
     * le RPi sait ainsi que la carte vient de (re)démarrer et lui renverra
     * ses consignes (T07) dès qu'elle sera prête. */
    etat_carte = HEARTBEAT_INITIALISATION;
    dernier_heartbeat_ms = HAL_GetTick();
    EnvoyerHeartbeat();

    return HAL_OK;
}

void CanEsa_Task(void)
{
    if (can == NULL)
    {
        return;
    }

    /* 1) Distribuer les trames reçues */
    while (rx_queue != rx_tete)
    {
        CanTrame trame = file_rx[rx_queue];

        rx_queue = (uint8_t)((rx_queue + 1U) % TAILLE_FILE_RX);
        Distribuer(&trame);
    }

    /* 2) Heartbeat toutes les 500 ms */
    if (HAL_GetTick() - dernier_heartbeat_ms >= CAN_PERIODE_HEARTBEAT_MS)
    {
        dernier_heartbeat_ms += CAN_PERIODE_HEARTBEAT_MS;
        EnvoyerHeartbeat();
    }

    /* 3) Envoyer ce qui attend */
    ViderFileEnvoi();

#if CAN_DEL_DIAGNOSTIC
    /* Orange : heartbeat du RPi reçu récemment.
     * Rouge : contrôleur CAN en erreur passive ou en bus-off
     * (souvent : bus non terminé, débit différent ou seul sur le bus). */
    uint32_t esr = can->Instance->ESR;

    HAL_GPIO_WritePin(LD3_GPIO_Port, LD3_Pin, CanEsa_RpiPresent() ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(LD5_GPIO_Port, LD5_Pin,
                      (esr & (CAN_ESR_BOFF | CAN_ESR_EPVF)) ? GPIO_PIN_SET : GPIO_PIN_RESET);
#endif
}

/* À appeler depuis la boucle principale seulement (pas sous interruption). */
HAL_StatusTypeDef CanEsa_Envoyer(uint16_t id, const uint8_t *donnees, uint8_t dlc)
{
    uint8_t suivant = (uint8_t)((tx_tete + 1U) % TAILLE_FILE_TX);

    if (dlc > 8U || (dlc > 0U && donnees == NULL))
    {
        return HAL_ERROR;
    }

    if (suivant == tx_queue)
    {
        nb_envois_perdus++;     /* file pleine : bus absent depuis longtemps */
        return HAL_BUSY;
    }

    file_tx[tx_tete].id = id;
    file_tx[tx_tete].dlc = dlc;
    memset(file_tx[tx_tete].donnees, 0, sizeof(file_tx[tx_tete].donnees));

    if (dlc > 0U)
    {
        memcpy(file_tx[tx_tete].donnees, donnees, dlc);
    }

    tx_tete = suivant;

    if (can != NULL)
    {
        ViderFileEnvoi();
    }

    return HAL_OK;
}

void CanEsa_DefinirEtat(uint8_t etat)
{
    etat_carte = etat;
}

uint8_t CanEsa_LireEtat(void)
{
    return etat_carte;
}

uint8_t CanEsa_RpiPresent(void)
{
    return rpi_deja_vu && (HAL_GetTick() - dernier_heartbeat_rpi_ms) <= CAN_DELAI_PERTE_RPI_MS;
}

uint32_t CanEsa_NbTramesPerdues(void)
{
    return nb_trames_perdues;
}

uint32_t CanEsa_NbEnvoisPerdus(void)
{
    return nb_envois_perdus;
}

/* ========================================================================= */
/* Interruption de réception (appelée par la HAL)                            */
/* ========================================================================= */
void HAL_CAN_RxFifo0MsgPendingCallback(CAN_HandleTypeDef *hcan)
{
    CAN_RxHeaderTypeDef entete;
    uint8_t donnees[8];

    while (HAL_CAN_GetRxFifoFillLevel(hcan, CAN_RX_FIFO0) > 0U)
    {
        if (HAL_CAN_GetRxMessage(hcan, CAN_RX_FIFO0, &entete, donnees) != HAL_OK)
        {
            return;
        }

        /* Seulement les trames de données à ID standard (protocole v1.6) */
        if (entete.IDE != CAN_ID_STD || entete.RTR != CAN_RTR_DATA)
        {
            continue;
        }

        uint8_t suivant = (uint8_t)((rx_tete + 1U) % TAILLE_FILE_RX);

        if (suivant == rx_queue)
        {
            nb_trames_perdues++;    /* boucle principale trop lente */
            continue;
        }

        file_rx[rx_tete].id = (uint16_t)entete.StdId;
        file_rx[rx_tete].dlc = (uint8_t)((entete.DLC <= 8U) ? entete.DLC : 8U);
        memcpy(file_rx[rx_tete].donnees, donnees, 8);
        rx_tete = suivant;
    }
}
