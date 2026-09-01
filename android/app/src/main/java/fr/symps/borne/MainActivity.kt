package fr.symps.borne

import android.annotation.SuppressLint
import android.app.Activity
import android.app.ActivityManager
import android.content.Context
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.WindowManager
import android.webkit.CookieManager
import android.webkit.WebResourceRequest
import android.webkit.WebResourceError
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.TextView
import java.net.HttpURLConnection
import java.net.URL

/**
 * La borne : un ecran, une page, rien d'autre.
 *
 * L'application ne contient aucune interface propre — tout vient du serveur de
 * la boutique. Elle ne fait que trois choses, mais elle les fait pour que
 * personne n'ait rien a saisir en magasin :
 *
 *   1. trouver l'hote sur le reseau local (voir [Decouverte]) ;
 *   2. afficher sa page en plein ecran, sans barre ni bouton ;
 *   3. y revenir toute seule quand le reseau a hoquete.
 *
 * L'adresse du dernier hote est retenue : au rallumage du matin, la borne
 * repart dessus immediatement et ne diffuse une recherche que si elle ne
 * repond plus.
 */
class MainActivity : Activity() {

    private lateinit var vue: WebView
    private lateinit var attente: View
    private lateinit var messageAttente: TextView
    private lateinit var boutonReessayer: Button

    private val prefs by lazy { getSharedPreferences("symps", Context.MODE_PRIVATE) }
    private var rechercheEnCours = false

    override fun onCreate(etatSauve: Bundle?) {
        super.onCreate(etatSauve)
        setContentView(R.layout.activity_principale)

        vue = findViewById(R.id.vue)
        attente = findViewById(R.id.attente)
        messageAttente = findViewById(R.id.message_attente)
        boutonReessayer = findViewById(R.id.bouton_reessayer)

        // Une borne allumee toute la journee ne doit jamais s'eteindre.
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        preparerVue()
        boutonReessayer.setOnClickListener { rejoindreHote() }
        rejoindreHote()
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun preparerVue() {
        vue.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            // La borne n'a pas besoin de zoom : c'est un ecran fixe, et un
            // client qui pince par megarde ne doit pas casser la mise en page.
            setSupportZoom(false)
            builtInZoomControls = false
            mediaPlaybackRequiresUserGesture = false
        }

        // Le role de l'appareil (« borne ») vit dans un cookie pose par le
        // serveur : il doit survivre a l'extinction de la tablette.
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(vue, true)

        vue.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                vue: WebView?,
                requete: WebResourceRequest?,
            ): Boolean = false  // tout reste dans l'application

            override fun onPageFinished(vue: WebView?, url: String?) {
                afficherPage()
            }

            override fun onReceivedError(
                vue: WebView?,
                requete: WebResourceRequest?,
                erreur: WebResourceError?,
            ) {
                // Seul l'echec de la page elle-meme compte : une image
                // manquante ne doit pas renvoyer la borne a l'ecran d'attente.
                if (requete?.isForMainFrame == true) {
                    afficherAttente(getString(R.string.hote_perdu))
                    rejoindreHote()
                }
            }
        }
    }

    /**
     * Rejoint l'hote : d'abord celui de la derniere fois, sinon on cherche.
     *
     * Tout se passe hors du fil principal — la recherche attend les reponses
     * pendant une seconde et demie, et l'ecran doit rester vivant.
     */
    private fun rejoindreHote() {
        if (rechercheEnCours) return
        rechercheEnCours = true
        afficherAttente(getString(R.string.recherche))

        Thread {
            val connu = prefs.getString("hote", null)
            val url = if (connu != null && repond(connu)) {
                connu
            } else {
                Decouverte.chercher(prefs.getString("atelier", "") ?: "")
                    .firstOrNull()
                    ?.url
                    ?.also { prefs.edit().putString("hote", it).apply() }
            }

            runOnUiThread {
                rechercheEnCours = false
                if (url == null) {
                    afficherAttente(getString(R.string.introuvable))
                } else {
                    vue.loadUrl(url)
                }
            }
        }.start()
    }

    /** L'hote connu est-il toujours la ? Une seconde d'attente, pas plus. */
    private fun repond(url: String): Boolean = try {
        (URL("$url/api/config").openConnection() as HttpURLConnection).run {
            connectTimeout = 1000
            readTimeout = 1000
            requestMethod = "GET"
            val vivant = responseCode in 200..499  // meme un refus prouve qu'il repond
            disconnect()
            vivant
        }
    } catch (erreur: Exception) {
        false
    }

    private fun afficherAttente(texte: String) {
        messageAttente.text = texte
        attente.visibility = View.VISIBLE
        vue.visibility = View.GONE
    }

    private fun afficherPage() {
        attente.visibility = View.GONE
        vue.visibility = View.VISIBLE
    }

    override fun onResume() {
        super.onResume()
        pleinEcran()
        epinglerEcran()
    }

    override fun onPause() {
        super.onPause()
        CookieManager.getInstance().flush()
    }

    /**
     * Epingle l'ecran : le client ne peut plus sortir de l'application.
     *
     * On ne le redemande pas si c'est deja fait — sans droit d'administrateur
     * d'appareil, Android affiche une confirmation, et la reposer a chaque
     * retour a l'ecran serait insupportable. Voir android/README.md pour le
     * verrouillage complet, sans aucune confirmation.
     */
    private fun epinglerEcran() {
        val gestionnaire = getSystemService(ACTIVITY_SERVICE) as? ActivityManager ?: return
        if (gestionnaire.lockTaskModeState != ActivityManager.LOCK_TASK_MODE_NONE) return
        try {
            startLockTask()
        } catch (erreur: Exception) {
            // Mode verrouille indisponible : l'application reste quittable.
        }
    }

    /** Ni barre de statut, ni barre de navigation : l'ecran est a la boutique. */
    private fun pleinEcran() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.setDecorFitsSystemWindows(false)
            window.insetsController?.let {
                it.hide(android.view.WindowInsets.Type.systemBars())
                it.systemBarsBehavior =
                    android.view.WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = (
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    or View.SYSTEM_UI_FLAG_FULLSCREEN
                    or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                )
        }
    }

    /**
     * Le retour arriere recule dans la page, mais ne quitte jamais l'application :
     * un client ne doit pas pouvoir tomber sur le bureau de la tablette.
     */
    @Suppress("DEPRECATION")
    override fun onBackPressed() {
        if (vue.visibility == View.VISIBLE && vue.canGoBack()) vue.goBack()
    }
}
