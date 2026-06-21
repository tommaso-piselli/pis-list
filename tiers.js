/* ============================================================================
   tiers.js  -  Configurazione dei SET (tier) per l'aggregatore di roster.html
   ----------------------------------------------------------------------------
   A cosa serve:
   I pezzi di set (testa, spalle, petto, mani, gambe) droppano come TOKEN
   condivisi da 3 classi. Nella BiS list hanno NOMI diversi per classe, ma sono
   lo stesso oggetto. Qui dico al visualizzatore come riconoscerli e unirli:

   - "groups": i 3 gruppi di classi che condividono lo stesso token.
   - "sets":   per ogni PAROLA che compare SEMPRE nel nome del set di una
               classe, indico a quale gruppo appartiene.
               (es. lo Shaman ha "Cataclysm" -> gruppo Champion)

   Cosi' se l'aggregatore incontra "Cataclysm Helm" (Shaman) e "Justicar Helm"
   (Paladino), capisce che sono lo STESSO token (Champion, slot Testa) e li conta
   come un'unica voce.

   La parola e' confrontata in modo case-insensitive come sottostringa del nome.
   Puoi usare una parola specifica per fase (es. "Cataclysm") oppure tenerne
   piu' d'una. Verifica/aggiorna i nomi secondo la fase della tua BiS list.
   Dopo aver modificato questo file basta RICARICARE la pagina (non serve
   rilanciare lo script).
   ============================================================================ */

window.BIS_TIERS = {

  // I 3 gruppi (come da tua indicazione). L'etichetta e' solo descrittiva.
  groups: {
    Champion: "Pala / Sham / Rogue",
    Hero: "Warlock / Mage / Hunter",
    Defender: "Warrior / Priest / Druid"
  },

  // parola_nel_nome : gruppo
  // (precompilati i nomi noti T4 / T5 / T6 - CONTROLLA e tieni quelli che ti servono)
  sets: {
    // --- gruppo Champion: Paladino / Shaman / Rogue ---
    "Justicar":      "Champion",   // Paladino T4
    "Crystalforge":  "Champion",   // Paladino T5
    "Lightbringer":  "Champion",   // Paladino T6
    "Cyclone":       "Champion",   // Shaman T4
    "Cataclysm":     "Champion",   // Shaman T5   <-- esempio che mi hai dato
    "Skyshatter":    "Champion",   // Shaman T6
    "Netherblade":   "Champion",   // Rogue T4
    "Deathmantle":   "Champion",   // Rogue T5
    "Slayer":        "Champion",   // Rogue T6

    // --- gruppo Hero: Warlock / Mage / Hunter ---
    "Voidheart":     "Hero",   // Warlock T4
    "Corruptor":     "Hero",   // Warlock T5
    "Malefic":       "Hero",   // Warlock T6
    "Tirisfal":      "Hero",   // Mage T5
    "Tempest":       "Hero",   // Mage T6
    "Rift Stalker":  "Hero",   // Hunter T5
    "Gronnstalker":  "Hero",   // Hunter T6
    "Demon Stalker": "Hero",   // Hunter T4

    // --- gruppo Defender: Warrior / Priest / Druid ---
    "Warbringer":    "Defender",   // Warrior T4
    "Destroyer":     "Defender",   // Warrior T5
    "Onslaught":     "Defender",   // Warrior T6
    "Incarnate":     "Defender",   // Priest T4
    "Avatar":        "Defender",   // Priest T5
    "Absolution":    "Defender",   // Priest T6
    "Malorne":       "Defender",   // Druid T4
    "Nordrassil":    "Defender",   // Druid T5
    "Thunderheart":  "Defender"    // Druid T6
  }
};
