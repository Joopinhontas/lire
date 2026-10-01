"""Server-side messages in the reader's language (French by default, English on request)."""
from contextvars import ContextVar

LANGS = ("fr", "en")
lang: ContextVar[str] = ContextVar("lang", default="fr")

MESSAGES = {
    "admin_only": {"fr": "Réservé à l'administrateur.", "en": "Admins only."},
    "slow_down": {"fr": "Doucement : trop de recherches d'un coup, réessaie dans une minute.",
                  "en": "Easy: too many searches at once, try again in a minute."},
    "too_many_tries": {"fr": "Trop d'essais, réessaie dans quelques minutes.",
                       "en": "Too many attempts, try again in a few minutes."},
    "bad_login": {"fr": "Identifiant ou mot de passe incorrect.", "en": "Wrong username or password."},
    "anilist_down": {"fr": "AniList ne répond pas ({err}).", "en": "AniList is not answering ({err})."},
    "search_down": {"fr": "Recherche impossible pour l'instant ({err}).", "en": "Search is unavailable right now ({err})."},
    "kavita_down": {"fr": "Kavita ne répond pas ({err}).", "en": "Kavita is not answering ({err})."},
    "two_letters": {"fr": "Tape au moins deux lettres.", "en": "Type at least two letters."},
    "reload_series": {"fr": "Recharge la fiche de la série puis réessaie.", "en": "Reload the series page and try again."},
    "reload_page": {"fr": "Recharge la page puis réessaie.", "en": "Reload the page and try again."},
    "unknown_release": {"fr": "sortie inconnue", "en": "unknown release"},
    "indexer_refused": {"fr": "l'indexeur a refusé le téléchargement", "en": "the indexer refused the download"},
    "not_in_library": {"fr": "Cette série n'est pas dans cette bibliothèque, supprime-la depuis Kavita.",
                       "en": "This series is not in this library, delete it from Kavita."},
    "shared_folder": {"fr": "Le dossier « {folder} » contient aussi : {names}. Rien n'a été supprimé.",
                      "en": "The folder \"{folder}\" also holds: {names}. Nothing was deleted."},
    "no_library": {"fr": "Kavita ne voit pas le dossier {folder} : monte-le dans le conteneur Kavita pour créer la bibliothèque « {library} ».",
                   "en": "Kavita cannot see the folder {folder}: mount it in the Kavita container so the \"{library}\" library can be created."},
    "no_kavita_account": {"fr": "Ton compte n'est pas encore relié à Kavita : reconnecte-toi à Lire.",
                          "en": "Your account is not linked to Kavita yet: sign in to Lire again."},
    "path_refused": {"fr": "Chemin refusé.", "en": "Path refused."},
    "bad_username": {"fr": "Identifiant : lettres minuscules, chiffres, point, tiret ou souligné (2 à 31 caractères).",
                     "en": "Username: lowercase letters, digits, dot, dash or underscore (2 to 31 characters)."},
    "user_exists": {"fr": "« {name} » existe déjà.", "en": "\"{name}\" already exists."},
    "kavita_user_failed": {"fr": "Le compte Kavita n'a pas pu être créé (le nom y existe peut-être déjà).",
                           "en": "The Kavita account could not be created (the name may already exist there)."},
    "kavita_password_kept": {"fr": "Mot de passe Kavita inchangé (compte Kavita introuvable).",
                             "en": "Kavita password unchanged (no Kavita account found)."},
    "no_such_user": {"fr": "Compte introuvable.", "en": "Account not found."},
    "keep_admin": {"fr": "Impossible de supprimer le compte administrateur.", "en": "The admin account cannot be deleted."},
}


def pick(header: str | None) -> str:
    """Language from the app header first, then the browser's Accept-Language."""
    for part in (header or "").replace(";", ",").split(","):
        code = part.strip().lower()[:2]
        if code in LANGS:
            return code
    return "fr"


def tr(key: str, **params) -> str:
    entry = MESSAGES[key]
    return entry.get(lang.get(), entry["fr"]).format(**params)
