import asyncio
import json
import re
import subprocess
import tempfile
import os
from urllib.parse import urlparse

import pandas as pd
from playwright.async_api import async_playwright


# ============================================================
# CONFIGURATION
# ============================================================

CITY = "Lannion"

BUSINESS_TYPES = [
    # Bâtiment / Artisans
    "Menuisier",
    "Ébéniste",
    "Plombier",
    "Électricien",
    "Peintre en bâtiment",
    "Couvreur",
    "Maçon",
    "Carreleur",
    "Plaquiste",
    "Façadier",
    "Serrurier",
    "Vitrier",
    "Chauffagiste",
    "Frigoriste",
    "Terrassier",
    "Paysagiste",
    "Jardinier",
    "Élagage",
    "Pisciniste",

    # Automobile
    "Garage automobile",
    "Carrosserie",
    "Contrôle technique",
    "Auto-école",
    "Lavage automobile",
    "Location de véhicules",
    "Réparation de pare-brise",
    "Vente de pneus",
    "Mécanicien moto",

    # Commerces alimentaires
    "Boulangerie",
    "Pâtisserie",
    "Boucherie",
    "Charcuterie",
    "Poissonnerie",
    "Fromagerie",
    "Primeur",
    "Épicerie",
    "Épicerie fine",
    "Chocolatier",
    "Caviste",
    "Traiteur",

    # Commerces
    "Fleuriste",
    "Cordonnier",
    "Bijouterie",
    "Librairie",
    "Papeterie",
    "Magasin de vêtements",
    "Magasin de chaussures",
    "Magasin de sport",
    "Magasin de décoration",
    "Magasin de meubles",
    "Magasin bio",
    "Animalerie",
    "Opticien",

    # Beauté / Bien-être
    "Coiffeur",
    "Barbier",
    "Institut de beauté",
    "Prothésiste ongulaire",
    "Tatoueur",
    "Salon de massage",
    "Spa",
    "Esthéticienne",
    "Maquilleuse",

    # Santé
    "Ostéopathe",
    "Kinésithérapeute",
    "Psychologue",
    "Naturopathe",
    "Pédicure podologue",
    "Orthophoniste",
    "Diététicien",
    "Sage-femme",
    "Dentiste",
    "Médecin généraliste",
    "Audioprothésiste",

    # Sport
    "Salle de sport",
    "Coach sportif",
    "Club de tennis",
    "Club de football",
    "Club de yoga",
    "Club de danse",
    "Piscine",

    # Restaurants / Hôtellerie
    "Restaurant",
    "Pizzeria",
    "Crêperie",
    "Snack",
    "Fast food",
    "Bar",
    "Café",
    "Salon de thé",
    "Hôtel",
    "Chambre d'hôtes",
    "Camping",

    # Services
    "Dépannage informatique",
    "Agence immobilière",
    "Assureur",
    "Courtier",
    "Expert-comptable",
    "Notaire",
    "Avocat",
    "Huissier",
    "Photographe",
    "Imprimerie",
    "Graphiste",
    "Traducteur",

    # Services à domicile
    "Ménage à domicile",
    "Aide à domicile",
    "Garde d'enfants",
    "Soutien scolaire",
    "Pet sitter",

    # Industrie / Pro
    "Métallerie",
    "Usinage",
    "Chaudronnerie",
    "Mécanique industrielle",
    "Fabrication industrielle",

    # Événementiel
    "DJ",
    "Location de matériel",
    "Wedding planner",
    "Organisateur d'événements",

    # Tourisme
    "Office de tourisme",
    "Location saisonnière",
    "Excursion",
    "Activités nautiques",

    # Tech
    "Agence de communication",
    "Consultant informatique"
]


# Nombre d'entreprises à analyser par secteur
MAX_RESULTS_PER_TYPE = 50


# Fichier final
OUTPUT_FILENAME = f"audit_sites_{CITY.lower()}.csv"


# ============================================================
# OUTILS
# ============================================================

def normalize_phone(phone):
    """
    Convertit un téléphone français vers :
    0612345678
    ou
    0712345678
    """

    if not phone:
        return None

    phone = re.sub(r"[^\d+]", "", phone)

    if phone.startswith("+33"):
        phone = "0" + phone[3:]

    elif phone.startswith("0033"):
        phone = "0" + phone[4:]

    if re.fullmatch(r"0[1-9]\d{8}", phone):
        return phone

    return None


# ============================================================
# TELEPHONE
# ============================================================

async def extract_phone(page):

    # --------------------------------------------------------
    # 1. Chercher un lien tel:
    # --------------------------------------------------------

    try:

        tel_links = page.locator('a[href^="tel:"]')

        count = await tel_links.count()

        for i in range(count):

            href = await tel_links.nth(i).get_attribute("href")

            if href:

                phone = href.replace(
                    "tel:",
                    ""
                )

                phone = normalize_phone(phone)

                if phone:
                    return phone

    except Exception:
        pass

    # --------------------------------------------------------
    # 2. Regex sur le texte
    # --------------------------------------------------------

    try:

        main = page.locator(
            'div[role="main"]'
        )

        if await main.count() == 0:
            return None

        text = await main.inner_text()

        pattern = (
            r'(?<!\d)'
            r'(?:'
            r'0[1-9](?:[\s.\-]*\d{2}){4}'
            r'|'
            r'(?:\+33|0033)[\s.\-]*[1-9]'
            r'(?:[\s.\-]*\d{2}){4}'
            r')'
            r'(?!\d)'
        )

        matches = re.findall(
            pattern,
            text
        )

        for match in matches:

            phone = normalize_phone(
                match
            )

            if phone:
                return phone

    except Exception:
        pass

    return None


# ============================================================
# NOM DE L'ENTREPRISE
# ============================================================

async def extract_business_name(page):

    selectors = [
        "h1.DUwDvf",
        "h1.fontHeadlineLarge",
        "h1"
    ]

    for selector in selectors:

        try:

            element = page.locator(
                selector
            ).first

            if await element.count() > 0:

                name = await element.inner_text()

                if name.strip():
                    return name.strip()

        except Exception:
            pass

    return "Inconnu"


# ============================================================
# SITE WEB
# ============================================================

async def extract_website(page):

    selectors = [
        'a[data-item-id="authority"]',
        'a[aria-label*="Site web"]',
        'a[aria-label*="site web"]',
        'a[aria-label*="Website"]',
        'a[aria-label*="website"]'
    ]

    for selector in selectors:

        try:

            links = page.locator(
                selector
            )

            count = await links.count()

            for i in range(count):

                href = await links.nth(i).get_attribute(
                    "href"
                )

                if href:

                    if href.startswith("http"):
                        return href

        except Exception:
            pass

    return None


# ============================================================
# OBTENIR LES ENTREPRISES DE GOOGLE MAPS
# ============================================================

async def get_businesses(
    page,
    query,
    max_results
):

    print()
    print("=" * 60)
    print(f"🔍 GOOGLE MAPS : {query}")
    print("=" * 60)

    search_url = (
        "https://www.google.com/maps/search/"
        + query.replace(" ", "+")
    )

    try:

        await page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=30000
        )

    except Exception as e:

        print(
            f"❌ Erreur Google Maps : {e}"
        )

        return []

    try:

        await page.wait_for_selector(
            'div[role="feed"]',
            timeout=10000
        )

    except Exception:

        print(
            "⚠️ Aucun résultat"
        )

        return []

    # --------------------------------------------------------
    # Scroll
    # --------------------------------------------------------

    for _ in range(
        max_results // 5 + 2
    ):

        try:

            await page.eval_on_selector(
                'div[role="feed"]',
                """
                el => {
                    el.scrollTop = el.scrollHeight;
                }
                """
            )

        except Exception:

            await page.mouse.wheel(
                0,
                3000
            )

        await asyncio.sleep(
            0.8
        )

    # --------------------------------------------------------
    # Récupération des cartes
    # --------------------------------------------------------

    cards = await page.locator(
        'div[role="article"]'
    ).all()

    businesses = []

    for card in cards[:max_results]:

        try:

            link = card.locator(
                'a[href*="/maps/place/"]'
            ).first

            if await link.count() == 0:
                continue

            maps_url = await link.get_attribute(
                "href"
            )

            if not maps_url:
                continue

            title = card.locator(
                "div.qBF1Pd"
            ).first

            if await title.count() > 0:

                name = (
                    await title.inner_text()
                ).strip()

            else:

                name = "Inconnu"

            businesses.append({
                "name": name,
                "maps_url": maps_url
            })

        except Exception:
            continue

    print(
        f"📋 {len(businesses)} entreprises trouvées"
    )

    return businesses


# ============================================================
# OUVRIR UNE ENTREPRISE GOOGLE MAPS
# ============================================================

async def open_business(
    page,
    business,
    sector
):

    try:

        await page.goto(
            business["maps_url"],
            wait_until="domcontentloaded",
            timeout=30000
        )

        await asyncio.sleep(
            1.5
        )

        name = await extract_business_name(
            page
        )

        phone = await extract_phone(
            page
        )

        website = await extract_website(
            page
        )

        if not website:

            print(
                f"   ❌ {name} : aucun site"
            )

            return None

        print(
            f"   🌐 {name}"
        )

        print(
            f"      {website}"
        )

        return {
            "Nom": name,
            "Secteur": sector,
            "Téléphone": (
                phone
                if phone
                else "Non spécifié"
            ),
            "Site": website,
            "Lien Google Maps": business[
                "maps_url"
            ]
        }

    except Exception as e:

        print(
            f"   ❌ Erreur fiche : {e}"
        )

        return None


# ============================================================
# LIGHTHOUSE
# ============================================================

def run_lighthouse(url):
    """
    Lance Lighthouse et retourne son JSON.
    """

    temp_file = tempfile.NamedTemporaryFile(
        suffix=".json",
        delete=False
    )

    temp_file.close()

    command = [
        "npx",
        "lighthouse",
        url,
        "--output=json",
        f"--output-path={temp_file.name}",
        "--quiet",
        "--chrome-flags=--headless",
        "--only-categories=performance,seo,accessibility,best-practices"
    ]

    try:

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:

            print(
                "      ⚠️ Lighthouse erreur"
            )

            return None

        with open(
            temp_file.name,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        return data

    except subprocess.TimeoutExpired:

        print(
            "      ⚠️ Lighthouse timeout"
        )

        return None

    except Exception as e:

        print(
            f"      ⚠️ Lighthouse : {e}"
        )

        return None

    finally:

        try:
            os.remove(
                temp_file.name
            )
        except Exception:
            pass


# ============================================================
# AUDIT PERSONNALISÉ DU SITE
# ============================================================

async def custom_audit(
    page,
    url
):

    result = {
        "HTTPS": False,
        "Viewport": False,
        "Title": False,
        "Meta Description": False,
        "H1": False,
        "Images Alt": False,
        "Favicon": False,
        "Formulaire": False,
        "Liens Internes": 0,
        "Liens Externes": 0,
        "Mots": 0,
        "Temps Chargement": 0
    }

    try:

        start = asyncio.get_event_loop().time()

        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30000
        )

        load_time = (
            asyncio.get_event_loop().time()
            - start
        )

        result[
            "Temps Chargement"
        ] = round(
            load_time,
            2
        )

    except Exception:

        return result

    # --------------------------------------------------------
    # HTTPS
    # --------------------------------------------------------

    result["HTTPS"] = (
        page.url.startswith(
            "https://"
        )
    )

    # --------------------------------------------------------
    # Viewport
    # --------------------------------------------------------

    try:

        viewport = await page.locator(
            'meta[name="viewport"]'
        ).count()

        result["Viewport"] = viewport > 0

    except Exception:
        pass

    # --------------------------------------------------------
    # Title
    # --------------------------------------------------------

    try:

        title = await page.title()

        result["Title"] = (
            len(title.strip()) > 0
        )

    except Exception:
        pass

    # --------------------------------------------------------
    # Meta description
    # --------------------------------------------------------

    try:

        description = page.locator(
            'meta[name="description"]'
        )

        if await description.count() > 0:

            content = await description.get_attribute(
                "content"
            )

            result[
                "Meta Description"
            ] = bool(
                content
                and content.strip()
            )

    except Exception:
        pass

    # --------------------------------------------------------
    # H1
    # --------------------------------------------------------

    try:

        result["H1"] = (
            await page.locator(
                "h1"
            ).count()
            > 0
        )

    except Exception:
        pass

    # --------------------------------------------------------
    # Images ALT
    # --------------------------------------------------------

    try:

        images = page.locator(
            "img"
        )

        image_count = await images.count()

        if image_count == 0:

            result[
                "Images Alt"
            ] = True

        else:

            missing_alt = 0

            for i in range(
                min(image_count, 100)
            ):

                alt = await images.nth(
                    i
                ).get_attribute(
                    "alt"
                )

                if alt is None:

                    missing_alt += 1

            result[
                "Images Alt"
            ] = (
                missing_alt == 0
            )

    except Exception:
        pass

    # --------------------------------------------------------
    # Favicon
    # --------------------------------------------------------

    try:

        result[
            "Favicon"
        ] = (
            await page.locator(
                'link[rel*="icon"]'
            ).count()
            > 0
        )

    except Exception:
        pass

    # --------------------------------------------------------
    # Formulaire
    # --------------------------------------------------------

    try:

        result[
            "Formulaire"
        ] = (
            await page.locator(
                "form"
            ).count()
            > 0
        )

    except Exception:
        pass

    # --------------------------------------------------------
    # Liens
    # --------------------------------------------------------

    try:

        links = page.locator(
            "a[href]"
        )

        count = await links.count()

        current_domain = urlparse(
            page.url
        ).netloc

        internal = 0
        external = 0

        for i in range(
            min(count, 300)
        ):

            href = await links.nth(
                i
            ).get_attribute(
                "href"
            )

            if not href:
                continue

            if href.startswith(
                ("#", "mailto:", "tel:", "javascript:")
            ):
                continue

            try:

                link_domain = urlparse(
                    href
                ).netloc

                if not link_domain:

                    internal += 1

                elif (
                    link_domain
                    == current_domain
                ):

                    internal += 1

                else:

                    external += 1

            except Exception:
                continue

        result[
            "Liens Internes"
        ] = internal

        result[
            "Liens Externes"
        ] = external

    except Exception:
        pass

    # --------------------------------------------------------
    # Nombre de mots
    # --------------------------------------------------------

    try:

        text = await page.locator(
            "body"
        ).inner_text()

        words = re.findall(
            r"\b[\wÀ-ÿ'-]+\b",
            text
        )

        result[
            "Mots"
        ] = len(words)

    except Exception:
        pass

    return result


# ============================================================
# CALCUL DU SCORE
# ============================================================

def calculate_score(
    lighthouse,
    custom
):

    # --------------------------------------------------------
    # Scores Lighthouse
    # --------------------------------------------------------

    if lighthouse:

        categories = lighthouse.get(
            "categories",
            {}
        )

        performance = round(
            categories.get(
                "performance",
                {}
            ).get(
                "score",
                0
            ) * 100
        )

        seo = round(
            categories.get(
                "seo",
                {}
            ).get(
                "score",
                0
            ) * 100
        )

        accessibility = round(
            categories.get(
                "accessibility",
                {}
            ).get(
                "score",
                0
            ) * 100
        )

        best_practices = round(
            categories.get(
                "best-practices",
                {}
            ).get(
                "score",
                0
            ) * 100
        )

    else:

        performance = 0
        seo = 0
        accessibility = 0
        best_practices = 0

    # --------------------------------------------------------
    # Mobile / responsive
    # --------------------------------------------------------

    mobile = 100

    if not custom["Viewport"]:
        mobile -= 50

    if custom["Temps Chargement"] > 5:
        mobile -= 30

    elif custom["Temps Chargement"] > 3:
        mobile -= 15

    mobile = max(
        0,
        mobile
    )

    # --------------------------------------------------------
    # Sécurité
    # --------------------------------------------------------

    security = 100

    if not custom["HTTPS"]:
        security -= 70

    security = max(
        0,
        security
    )

    # --------------------------------------------------------
    # Contenu
    # --------------------------------------------------------

    content = 100

    if not custom["Title"]:
        content -= 25

    if not custom["Meta Description"]:
        content -= 20

    if not custom["H1"]:
        content -= 20

    if custom["Mots"] < 100:
        content -= 20

    elif custom["Mots"] < 250:
        content -= 10

    if custom["Liens Internes"] < 2:
        content -= 15

    content = max(
        0,
        content
    )

    # --------------------------------------------------------
    # Technique
    # --------------------------------------------------------

    technical = 100

    if not custom["Favicon"]:
        technical -= 10

    if not custom["Images Alt"]:
        technical -= 20

    if custom["Liens Internes"] == 0:
        technical -= 20

    if custom["Temps Chargement"] > 5:
        technical -= 20

    if not custom["Viewport"]:
        technical -= 20

    technical = max(
        0,
        technical
    )

    # --------------------------------------------------------
    # SCORE GLOBAL
    # --------------------------------------------------------

    global_score = (
        seo * 0.25
        + performance * 0.25
        + mobile * 0.15
        + accessibility * 0.10
        + best_practices * 0.10
        + security * 0.05
        + content * 0.05
        + technical * 0.05
    )

    global_score = round(
        global_score
    )

    # --------------------------------------------------------
    # Problèmes détectés
    # --------------------------------------------------------

    problems = []

    if seo < 60:
        problems.append(
            "SEO faible"
        )

    if performance < 50:
        problems.append(
            "Site lent"
        )

    elif performance < 70:
        problems.append(
            "Performance moyenne"
        )

    if mobile < 60:
        problems.append(
            "Mauvaise compatibilité mobile"
        )

    if accessibility < 60:
        problems.append(
            "Accessibilité faible"
        )

    if best_practices < 60:
        problems.append(
            "Mauvaises pratiques techniques"
        )

    if not custom["HTTPS"]:
        problems.append(
            "Pas de HTTPS"
        )

    if not custom["Title"]:
        problems.append(
            "Pas de balise title"
        )

    if not custom["Meta Description"]:
        problems.append(
            "Pas de meta description"
        )

    if not custom["H1"]:
        problems.append(
            "Pas de H1"
        )

    if not custom["Images Alt"]:
        problems.append(
            "Images sans ALT"
        )

    if custom["Mots"] < 100:
        problems.append(
            "Très peu de contenu"
        )

    if not custom["Formulaire"]:
        problems.append(
            "Pas de formulaire"
        )

    if not custom["Viewport"]:
        problems.append(
            "Pas de configuration mobile"
        )

    # --------------------------------------------------------
    # Catégorie
    # --------------------------------------------------------

    if global_score >= 80:
        classification = "Excellent"

    elif global_score >= 65:
        classification = "Correct"

    elif global_score >= 50:
        classification = "Moyen"

    elif global_score >= 35:
        classification = "Mauvais"

    else:
        classification = "Très mauvais"

    return {
        "Score Global": global_score,
        "Score SEO": seo,
        "Score Performance": performance,
        "Score Mobile": mobile,
        "Score Accessibilité": accessibility,
        "Score Bonnes pratiques": best_practices,
        "Score Sécurité": security,
        "Score Contenu": content,
        "Score Technique": technical,
        "Classification": classification,
        "Problèmes": " | ".join(
            problems
        )
    }


# ============================================================
# AUDIT D'UN SITE
# ============================================================

async def audit_website(
    page,
    business
):

    name = business["Nom"]
    url = business["Site"]

    print()
    print(
        f"   🔎 AUDIT : {name}"
    )

    print(
        f"      {url}"
    )

    # --------------------------------------------------------
    # Lighthouse
    # --------------------------------------------------------

    print(
        "      ⏳ Lighthouse..."
    )

    lighthouse = await asyncio.to_thread(
        run_lighthouse,
        url
    )

    # --------------------------------------------------------
    # Audit personnalisé
    # --------------------------------------------------------

    print(
        "      🔧 Analyse technique..."
    )

    custom = await custom_audit(
        page,
        url
    )

    # --------------------------------------------------------
    # Score
    # --------------------------------------------------------

    scores = calculate_score(
        lighthouse,
        custom
    )

    print(
        f"      ⭐ Score : "
        f"{scores['Score Global']}/100 "
        f"({scores['Classification']})"
    )

    print(
        f"      SEO : "
        f"{scores['Score SEO']}/100"
    )

    print(
        f"      Performance : "
        f"{scores['Score Performance']}/100"
    )

    return {
        **business,
        **scores,
        "HTTPS": custom[
            "HTTPS"
        ],
        "Viewport": custom[
            "Viewport"
        ],
        "Title": custom[
            "Title"
        ],
        "Meta Description": custom[
            "Meta Description"
        ],
        "H1": custom[
            "H1"
        ],
        "Images ALT": custom[
            "Images Alt"
        ],
        "Favicon": custom[
            "Favicon"
        ],
        "Formulaire": custom[
            "Formulaire"
        ],
        "Liens Internes": custom[
            "Liens Internes"
        ],
        "Liens Externes": custom[
            "Liens Externes"
        ],
        "Nombre de mots": custom[
            "Mots"
        ],
        "Temps Chargement": custom[
            "Temps Chargement"
        ]
    }


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

async def main():

    all_results = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        context = await browser.new_context(

            user_agent=(
                "Mozilla/5.0 "
                "(Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/122.0.0.0 "
                "Safari/537.36"
            ),

            locale="fr-FR",

            viewport={
                "width": 1440,
                "height": 900
            }
        )

        maps_page = await context.new_page()

        audit_page = await context.new_page()

        # ----------------------------------------------------
        # Cookies Google Maps
        # ----------------------------------------------------

        try:

            await maps_page.goto(
                "https://www.google.com/maps",
                wait_until="domcontentloaded",
                timeout=30000
            )

            await asyncio.sleep(1)

            buttons = maps_page.locator(
                "button:has-text('Tout accepter'), "
                "button:has-text('Accept all'), "
                "button:has-text('Tout refuser')"
            )

            if await buttons.count() > 0:

                try:

                    await buttons.first.click(
                        timeout=4000
                    )

                except Exception:
                    pass

        except Exception:
            pass

        # ----------------------------------------------------
        # Secteurs
        # ----------------------------------------------------

        for business_type in BUSINESS_TYPES:

            query = (
                f"{business_type} {CITY}"
            )

            businesses = await get_businesses(
                maps_page,
                query,
                MAX_RESULTS_PER_TYPE
            )

            # ------------------------------------------------
            # Ouverture des fiches
            # ------------------------------------------------

            for business in businesses:

                data = await open_business(
                    maps_page,
                    business,
                    business_type
                )

                if not data:
                    continue

                # ------------------------------------------------
                # Audit du site
                # ------------------------------------------------

                result = await audit_website(
                    audit_page,
                    data
                )

                if result:

                    all_results.append(
                        result
                    )

                await asyncio.sleep(
                    1
                )

            await asyncio.sleep(
                2
            )

        await browser.close()

    # ========================================================
    # CSV
    # ========================================================

    if not all_results:

        print()
        print(
            "❌ Aucun site analysé."
        )

        return

    df = pd.DataFrame(
        all_results
    )

    # --------------------------------------------------------
    # Nettoyage téléphone
    # --------------------------------------------------------

    df["Téléphone"] = df[
        "Téléphone"
    ].apply(
        lambda x:
            normalize_phone(x)
            if x != "Non spécifié"
            else x
    )

    # --------------------------------------------------------
    # Suppression doublons
    # --------------------------------------------------------

    df = df.drop_duplicates(
        subset=[
            "Nom",
            "Site"
        ]
    )

    # --------------------------------------------------------
    # Tri : mauvais sites en premier
    # --------------------------------------------------------

    df = df.sort_values(
        by=[
            "Score Global"
        ],
        ascending=True
    )

    # --------------------------------------------------------
    # Export
    # --------------------------------------------------------

    df.to_csv(
        OUTPUT_FILENAME,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # STATISTIQUES
    # ========================================================

    print()
    print("=" * 60)
    print("🎉 AUDIT TERMINÉ")
    print("=" * 60)

    print(
        f"🌐 Sites analysés : "
        f"{len(df)}"
    )

    print(
        f"🔴 Très mauvais : "
        f"{len(df[df['Score Global'] < 35])}"
    )

    print(
        f"🟠 Mauvais : "
        f"{len(df[(df['Score Global'] >= 35) & (df['Score Global'] < 50)])}"
    )

    print(
        f"🟡 Moyens : "
        f"{len(df[(df['Score Global'] >= 50) & (df['Score Global'] < 65)])}"
    )

    print(
        f"🟢 Corrects : "
        f"{len(df[(df['Score Global'] >= 65) & (df['Score Global'] < 80)])}"
    )

    print(
        f"🔵 Excellents : "
        f"{len(df[df['Score Global'] >= 80])}"
    )

    print()
    print(
        f"📁 CSV : {OUTPUT_FILENAME}"
    )

    print("=" * 60)


# ============================================================
# LANCEMENT
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())