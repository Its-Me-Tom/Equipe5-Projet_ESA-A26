/*
 * t07_eclairage.c
 *
 *  T07 — DEL d'état des places et éclairage blanc (voir t07_eclairage.h).
 *  Responsable : Tom
 *
 *  Tout est non bloquant : pas de HAL_Delay(). Le clignotement et la
 *  décoration avancent avec HAL_GetTick() dans LED_Task().
 */

#include "t07_eclairage.h"
#include "apa102.h"
#include "carte_config.h"
#include "protocole_can.h"

extern SPI_HandleTypeDef T07_SPI_HANDLE;

/* ========================================================================= */
/* MAPPAGE — numéro des DEL dans la chaîne (1 = première DEL après le       */
/* connecteur). À valider sur banc (point 1 de la fiche T07).               */
/* ========================================================================= */

/* DEL de chaque place de la plaque : place locale 0 -> DEL 2, etc. */
static const uint8_t del_des_places[T07_NB_PLACES] = { 2, 4, 6, 8, 10, 12, 14 };

/* DEL de l'éclairage blanc (dessous de la plaque) */
static const uint8_t del_eclairage[] = { 1, 3, 5, 7, 9, 11, 13, 15 };

#define NB_DEL_ECLAIRAGE (sizeof(del_eclairage) / sizeof(del_eclairage[0]))

/* ========================================================================= */
/* Réglages de temps                                                         */
/* ========================================================================= */
#define DEMI_PERIODE_CLIGNOTEMENT_MS  500U   /* 1 Hz : 500 ms allumé, 500 ms éteint */
#define PERIODE_RAFRAICHISSEMENT_MS   1000U  /* renvoi de sécurité de toute la chaîne */
#define PERIODE_DISCO_MS              40U    /* vitesse de l'arc-en-ciel */
#define PERIODE_DEMO_MS               2000U  /* durée de chaque état en mode démo */

/* ========================================================================= */
/* Couleurs des états logiques (identiques à COULEURS_DEL du RPi)            */
/* ========================================================================= */
static const uint8_t couleurs_etats[T07_NB_ETATS][4] =
{
    /* rouge, vert, bleu, mode */
    {   0, 255,   0, DEL_MODE_FIXE       },  /* LIBRE       : vert             */
    {   0,   0, 255, DEL_MODE_FIXE       },  /* RESERVE     : bleu             */
    { 255,   0,   0, DEL_MODE_FIXE       },  /* OCCUPE      : rouge            */
    { 255, 165,   0, DEL_MODE_FIXE       },  /* MAINTENANCE : orange           */
    { 255, 255,   0, DEL_MODE_CLIGNOTANT },  /* DEFAUT      : jaune clignotant */
    {   0,   0,   0, DEL_MODE_FIXE       },  /* ETEINT                         */
};

/* ========================================================================= */
/* Variables                                                                 */
/* ========================================================================= */
typedef struct
{
    uint8_t rouge;
    uint8_t vert;
    uint8_t bleu;
    uint8_t mode;       /* DEL_MODE_FIXE ou DEL_MODE_CLIGNOTANT */
} ConsignePlace;

static APA102_HandleTypeDef barre;
static uint8_t initialise = 0;

/* Dernières consignes reçues (gardées en RAM seulement, comme le prévoit
 * le contrat : le RPi les renvoie après un redémarrage) */
static ConsignePlace places[T07_NB_PLACES];
static APA102_Couleur eclairage;

static uint8_t a_rafraichir = 0;
static uint8_t phase_eteinte = 0;           /* 1 = moitié « éteinte » du clignotement */
static uint32_t dernier_envoi_ms = 0;

#if !T07_A_DES_PLACES && T07_DISCO
static uint8_t position_disco = 0;
static uint32_t dernier_pas_disco_ms = 0;
#endif

#if T07_ETAT_SUR_PERTE_RPI
static uint8_t rpi_etait_present = 0;
#endif

/* ========================================================================= */
/* Fonctions internes                                                        */
/* ========================================================================= */

/* Applique la calibration du blanc (en %) à une composante */
static uint8_t Calibrer(uint8_t valeur, uint32_t pourcentage)
{
    uint32_t resultat = ((uint32_t)valeur * pourcentage) / 100U;

    return (uint8_t)((resultat > 255U) ? 255U : resultat);
}

#if !T07_A_DES_PLACES && T07_DISCO
/* Roue de couleurs : 0 à 255 -> rouge, vert, bleu, puis retour au rouge */
static APA102_Couleur RoueCouleurs(uint8_t position)
{
    APA102_Couleur c;

    if (position < 85U)
    {
        c.rouge = (uint8_t)(255U - position * 3U);
        c.vert = (uint8_t)(position * 3U);
        c.bleu = 0;
    }
    else if (position < 170U)
    {
        position = (uint8_t)(position - 85U);
        c.rouge = 0;
        c.vert = (uint8_t)(255U - position * 3U);
        c.bleu = (uint8_t)(position * 3U);
    }
    else
    {
        position = (uint8_t)(position - 170U);
        c.rouge = (uint8_t)(position * 3U);
        c.vert = 0;
        c.bleu = (uint8_t)(255U - position * 3U);
    }

    return c;
}
#endif

static uint8_t UnePlaceClignote(void)
{
    for (uint32_t i = 0; i < T07_NB_PLACES; i++)
    {
        if (places[i].mode == DEL_MODE_CLIGNOTANT)
        {
            return 1;
        }
    }

    return 0;
}

/* Remplit la chaîne à partir des consignes, sans l'envoyer */
static void ConstruireBarre(void)
{
    APA102_ToutEteindre(&barre);

    /* Éclairage blanc : DEL impaires */
    uint8_t r = Calibrer(eclairage.rouge, T07_CALIB_ROUGE_PCT);
    uint8_t v = Calibrer(eclairage.vert, T07_CALIB_VERT_PCT);
    uint8_t b = Calibrer(eclairage.bleu, T07_CALIB_BLEU_PCT);

    for (uint32_t i = 0; i < NB_DEL_ECLAIRAGE; i++)
    {
        APA102_DefinirCouleur(&barre, (uint8_t)(del_eclairage[i] - 1U), r, v, b);
    }

    /* DEL paires : places, ou décoration sur une plaque sans places */
    for (uint32_t i = 0; i < T07_NB_PLACES; i++)
    {
        uint8_t indice = (uint8_t)(del_des_places[i] - 1U);

#if T07_A_DES_PLACES
        if (places[i].mode == DEL_MODE_CLIGNOTANT && phase_eteinte)
        {
            continue;   /* reste éteinte pendant cette demi-période */
        }

        APA102_DefinirCouleur(&barre, indice, places[i].rouge, places[i].vert, places[i].bleu);
#elif T07_DISCO
        /* Chaque DEL est décalée sur la roue : l'arc-en-ciel défile */
        APA102_Couleur c = RoueCouleurs((uint8_t)(position_disco + i * 36U));

        APA102_DefinirCouleur(&barre, indice, c.rouge, c.vert, c.bleu);
#else
        (void)indice;   /* plaque sans places et sans déco : DEL éteintes */
#endif
    }
}

static void EnvoyerAccuse(uint16_t id, uint8_t sequence, uint8_t reference, bool applique)
{
    uint8_t donnees[3];

    donnees[0] = sequence;
    donnees[1] = reference;     /* place 1-14 ou niveau 0-2, tel que reçu */
    donnees[2] = applique ? ACCUSE_APPLIQUE : ACCUSE_REFUSE;

    CanEsa_Envoyer(id, donnees, 3);
}

/* DEL_PLACE_CMD (0x340) : DB0 séq., DB1 place 1-14, DB2-DB4 RVB, DB5 mode */
static void TraiterDelPlace(const CanTrame *trame)
{
#if T07_A_DES_PLACES
    if (trame->dlc < 2U)
    {
        return;     /* ni séquence ni place : impossible de répondre */
    }

    uint8_t sequence = trame->donnees[0];
    uint8_t place = trame->donnees[1];
    bool place_existe = (place >= 1U && place <= 14U);
    bool place_a_moi = (place >= T07_PREMIERE_PLACE &&
                        place < T07_PREMIERE_PLACE + T07_NB_PLACES);

    /* Place valide de l'autre carte : c'est elle qui répondra */
    if (place_existe && !place_a_moi)
    {
        return;
    }

    bool applique = false;

#if !T07_MODE_DEMO
    if (place_a_moi && trame->dlc == 6U)
    {
        applique = LED_DefinirCouleurPlace((uint8_t)(place - T07_PREMIERE_PLACE),
                                           trame->donnees[2],
                                           trame->donnees[3],
                                           trame->donnees[4],
                                           trame->donnees[5]);
    }
#endif

    /* Place 0 ou > 14, DLC faux, mode inconnu ou mode démo : refusé */
    EnvoyerAccuse(T07_ID_ACCUSE_DEL, sequence, place, applique);
#else
    (void)trame;    /* cette carte n'a pas de places */
#endif
}

/* ECLAIRAGE_CMD (0x130) : DB0 séq., DB1 niveau 0-2, DB2-DB4 RVB (R = V = B) */
static void TraiterEclairage(const CanTrame *trame)
{
    if (trame->dlc < 2U)
    {
        return;
    }

    uint8_t sequence = trame->donnees[0];
    uint8_t niveau = trame->donnees[1];

    /* Niveau valide d'une autre carte : c'est elle qui répondra */
    if (niveau <= 2U && niveau != T07_NIVEAU_ECLAIRAGE)
    {
        return;
    }

    bool applique = false;

#if !T07_MODE_DEMO
    if (niveau == T07_NIVEAU_ECLAIRAGE && trame->dlc == 5U)
    {
        applique = RGB_DefinirCouleur(trame->donnees[2], trame->donnees[3], trame->donnees[4]);
    }
#endif

    /* Niveau > 2, DLC faux ou mode démo : refusé */
    EnvoyerAccuse(T07_ID_ACCUSE_ECLAIRAGE, sequence, niveau, applique);
}

#if T07_MODE_DEMO
/* Fait défiler tous les états sur les places et varier l'éclairage,
 * pour vérifier les couleurs et le mappage sans RPi. */
static void AvancerDemo(uint32_t maintenant)
{
    static uint32_t dernier_pas_ms = 0;
    static uint8_t pas = 0;
    static const uint8_t intensites[] = { 0, 32, 128, 255 };

    if (maintenant - dernier_pas_ms < PERIODE_DEMO_MS)
    {
        return;
    }

    dernier_pas_ms = maintenant;

    for (uint8_t i = 0; i < T07_NB_PLACES; i++)
    {
        /* Décalage par place : on voit plusieurs couleurs à la fois */
        LED_DefinirEtatPlace(i, (uint8_t)((pas + i) % T07_ETAT_ETEINT));
    }

    RGB_DefinirIntensite(intensites[pas % sizeof(intensites)]);
    pas++;
}
#endif

/* ========================================================================= */
/* Fonctions publiques                                                       */
/* ========================================================================= */

void LED_Init(void)
{
#ifdef CS_I2C_SPI_Pin
    /* L'accéléromètre de la Discovery partage le SPI1 : CS haut = désélectionné */
    HAL_GPIO_WritePin(CS_I2C_SPI_GPIO_Port, CS_I2C_SPI_Pin, GPIO_PIN_SET);
#endif

    for (uint32_t i = 0; i < T07_NB_PLACES; i++)
    {
        places[i].rouge = 0;
        places[i].vert = 0;
        places[i].bleu = 0;
        places[i].mode = DEL_MODE_FIXE;
    }

    /* Au démarrage, tout est éteint jusqu'à la première consigne du RPi */
    eclairage.rouge = 0;
    eclairage.vert = 0;
    eclairage.bleu = 0;

    APA102_Init(&barre, &T07_SPI_HANDLE, T07_NB_DEL, T07_LUMINOSITE_GLOBALE);

    dernier_envoi_ms = HAL_GetTick();
    a_rafraichir = 0;
    initialise = 1;
}

void LED_Task(void)
{
    if (!initialise)
    {
        return;
    }

    uint32_t maintenant = HAL_GetTick();

#if T07_MODE_DEMO
    AvancerDemo(maintenant);
#endif

#if T07_ETAT_SUR_PERTE_RPI && !T07_MODE_DEMO
    /* Le RPi vient de disparaître : état sûr */
    uint8_t rpi_present = CanEsa_RpiPresent();

    if (rpi_etait_present && !rpi_present)
    {
        LED_AppliquerEtatSur();
    }

    rpi_etait_present = rpi_present;
#endif

    /* Clignotement 1 Hz, en phase pour toutes les places */
    uint8_t phase = (uint8_t)((maintenant / DEMI_PERIODE_CLIGNOTEMENT_MS) % 2U);

    if (phase != phase_eteinte)
    {
        phase_eteinte = phase;

        if (UnePlaceClignote())
        {
            a_rafraichir = 1;
        }
    }

#if !T07_A_DES_PLACES && T07_DISCO
    if (maintenant - dernier_pas_disco_ms >= PERIODE_DISCO_MS)
    {
        dernier_pas_disco_ms = maintenant;
        position_disco++;
        a_rafraichir = 1;
    }
#endif

    /* Renvoi périodique : corrige une DEL perturbée par un parasite */
    if (maintenant - dernier_envoi_ms >= PERIODE_RAFRAICHISSEMENT_MS)
    {
        a_rafraichir = 1;
    }

    if (a_rafraichir)
    {
        ConstruireBarre();
        APA102_Envoyer(&barre);
        dernier_envoi_ms = maintenant;
        a_rafraichir = 0;
    }
}

bool LED_DefinirEtatPlace(uint8_t place, uint8_t etat)
{
    if (etat >= T07_NB_ETATS)
    {
        return false;
    }

    return LED_DefinirCouleurPlace(place,
                                   couleurs_etats[etat][0],
                                   couleurs_etats[etat][1],
                                   couleurs_etats[etat][2],
                                   couleurs_etats[etat][3]);
}

bool LED_DefinirCouleurPlace(uint8_t place, uint8_t rouge, uint8_t vert, uint8_t bleu, uint8_t mode)
{
#if T07_A_DES_PLACES
    if (place >= T07_NB_PLACES || mode > DEL_MODE_CLIGNOTANT)
    {
        return false;
    }

    places[place].rouge = rouge;
    places[place].vert = vert;
    places[place].bleu = bleu;
    places[place].mode = mode;
    a_rafraichir = 1;

    return true;
#else
    (void)place; (void)rouge; (void)vert; (void)bleu; (void)mode;
    return false;   /* plaque sans places */
#endif
}

bool RGB_DefinirIntensite(uint8_t intensite)
{
    return RGB_DefinirCouleur(intensite, intensite, intensite);
}

bool RGB_DefinirCouleur(uint8_t rouge, uint8_t vert, uint8_t bleu)
{
    /* Toutes les valeurs 0-255 sont valides : rien à refuser */
    eclairage.rouge = rouge;
    eclairage.vert = vert;
    eclairage.bleu = bleu;
    a_rafraichir = 1;

    return true;
}

/* État sûr : toutes les places en « défaut » (jaune clignotant), éclairage
 * conservé (mieux vaut voir clair en cas de problème). */
void LED_AppliquerEtatSur(void)
{
    for (uint8_t i = 0; i < T07_NB_PLACES; i++)
    {
        LED_DefinirEtatPlace(i, T07_ETAT_DEFAUT);
    }
}

uint8_t T07_TraiterTrameCan(const CanTrame *trame)
{
    switch (trame->id)
    {
        case DEL_PLACE_CMD:
            TraiterDelPlace(trame);
            return 1;

        case ECLAIRAGE_CMD:
            TraiterEclairage(trame);
            return 1;

        default:
            return 0;   /* pas une trame de T07 */
    }
}
