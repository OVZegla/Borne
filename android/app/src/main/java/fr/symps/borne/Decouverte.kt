package fr.symps.borne

import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.NetworkInterface
import java.net.SocketTimeoutException

/**
 * Trouve l'hote Symp's Kiosk sur le reseau local.
 *
 * Le meme dialogue que `kiosk/reseau.py`, cote tablette :
 *
 *     borne  -->  diffusion   SYMPS?1 <atelier>
 *     hote   -->  reponse     SYMPS!1 {"host": "...", "port": 8080, ...}
 *
 * C'est ce qui permet a la borne de n'avoir aucune adresse a saisir : on la
 * pose sur le Wi-Fi de la boutique, elle trouve la machine toute seule.
 */
data class Hote(val adresse: String, val port: Int, val nom: String) {
    val url: String get() = "http://$adresse:$port"
}

object Decouverte {

    private const val PORT_DECOUVERTE = 8079
    private const val PROTOCOLE = 1
    private val QUESTION = "SYMPS?$PROTOCOLE ".toByteArray()
    private val REPONSE = "SYMPS!$PROTOCOLE ".toByteArray()
    private const val TAILLE_MAX = 2048

    /**
     * Diffuse une recherche et retourne les hotes qui repondent.
     *
     * A appeler hors du fil principal : la methode attend les reponses pendant
     * [dureeMs]. Un atelier vide interroge tout le monde ; renseigne, il evite
     * de tomber sur l'hote de la boutique voisine sur un reseau partage.
     */
    fun chercher(atelier: String = "", dureeMs: Long = 1500): List<Hote> {
        val trouves = LinkedHashMap<String, Hote>()
        val prise = try {
            DatagramSocket().apply {
                broadcast = true
                soTimeout = 300
            }
        } catch (erreur: Exception) {
            return emptyList()
        }

        try {
            val question = QUESTION + atelier.toByteArray()
            for (cible in adressesDeDiffusion()) {
                try {
                    prise.send(DatagramPacket(question, question.size, cible, PORT_DECOUVERTE))
                } catch (erreur: Exception) {
                    // Une interface qui refuse la diffusion n'empeche pas les autres.
                }
            }

            val fin = System.currentTimeMillis() + dureeMs
            val tampon = ByteArray(TAILLE_MAX)
            while (System.currentTimeMillis() < fin) {
                val paquet = DatagramPacket(tampon, tampon.size)
                try {
                    prise.receive(paquet)
                } catch (erreur: SocketTimeoutException) {
                    continue
                } catch (erreur: Exception) {
                    break
                }
                lire(paquet, atelier)?.let { trouves[it.url] = it }
            }
        } finally {
            prise.close()
        }
        return trouves.values.toList()
    }

    /** Interprete une reponse, ou null si le paquet n'est pas des notres. */
    private fun lire(paquet: DatagramPacket, atelier: String): Hote? {
        if (paquet.length <= REPONSE.size) return null
        for (i in REPONSE.indices) {
            if (paquet.data[paquet.offset + i] != REPONSE[i]) return null
        }

        val corps = String(
            paquet.data,
            paquet.offset + REPONSE.size,
            paquet.length - REPONSE.size,
            Charsets.UTF_8,
        )
        val fiche = try {
            JSONObject(corps)
        } catch (erreur: Exception) {
            return null
        }

        val port = fiche.optInt("port", 0)
        if (port <= 0) return null
        if (atelier.isNotEmpty() && fiche.optString("atelier") != atelier) return null

        // L'adresse vue par le reseau prime sur celle que l'hote declare : elle
        // est juste meme si la machine a plusieurs interfaces.
        val adresse = paquet.address?.hostAddress ?: return null
        return Hote(adresse, port, fiche.optString("nom", adresse))
    }

    /**
     * Les adresses de diffusion a interroger.
     *
     * On passe par les interfaces plutot que par le seul Wi-Fi : une borne peut
     * tres bien etre branchee en Ethernet. `255.255.255.255` est ajoutee en
     * dernier recours, certains reseaux ne relayant que celle du sous-reseau.
     */
    private fun adressesDeDiffusion(): List<InetAddress> {
        val adresses = mutableListOf<InetAddress>()
        try {
            for (interfaceReseau in NetworkInterface.getNetworkInterfaces()) {
                if (!interfaceReseau.isUp || interfaceReseau.isLoopback) continue
                for (adresse in interfaceReseau.interfaceAddresses) {
                    adresse.broadcast?.let { adresses.add(it) }
                }
            }
        } catch (erreur: Exception) {
            // Pas d'interface lisible : il reste la diffusion generale.
        }
        try {
            adresses.add(InetAddress.getByName("255.255.255.255"))
        } catch (erreur: Exception) {
            // Rien de plus a tenter.
        }
        return adresses
    }
}
