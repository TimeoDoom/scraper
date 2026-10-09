import asyncio
import re
from playwright.async_api import async_playwright
import pandas as pd


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
    "Agence web",
    "Agence de communication",
    "Consultant informatique",
    "Développeur freelance"
]

MAX_RESULTS_PER_TYPE = 80

OUTPUT_FILENAME = f"leads_sans_site_{CITY.lower()}.csv"


# ============================================================
# NORMALISATION DU TELEPHONE
# ============================================================

def normalize_phone(phone):
    """
    Transforme les numéros français en format :
    0612345678
    0712345678
    """

    if not phone:
        return None

    # Supprime tout sauf les chiffres et +
    phone = re.sub(r"[^\d+]", "", phone)

    # +33XXXXXXXXX -> 0XXXXXXXXX
    if phone.startswith("+33"):
        phone = "0" + phone[3:]

    # 0033XXXXXXXXX -> 0XXXXXXXXX
    elif phone.startswith("0033"):
        phone = "0" + phone[4:]

    # Vérification d'un numéro français classique
    if re.fullmatch(r"0[1-9]\d{8}", phone):
        return phone

    return None


# ============================================================
# EXTRACTION DU TELEPHONE
# ============================================================

async def extract_phone(page):
    """
    Cherche d'abord un lien tel:
    puis cherche le numéro dans le texte de la fiche.
    """

    # --------------------------------------------------------
    # Méthode 1 : lien tel:
    # --------------------------------------------------------

    tel_links = page.locator('a[href^="tel:"]')

    try:
        count = await tel_links.count()

        for i in range(count):
            href = await tel_links.nth(i).get_attribute("href")

            if href:
                phone = href.replace("tel:", "").strip()
                phone = normalize_phone(phone)

                if phone:
                    return phone

    except Exception:
        pass

    # --------------------------------------------------------
    # Méthode 2 : texte de la fiche
    # --------------------------------------------------------

    try:
        main = page.locator('div[role="main"]')

        if await main.count() > 0:
            text = await main.inner_text()

            # Numéros français :
            #
            # 0612345678
            # 06 12 34 56 78
            # 06.12.34.56.78
            # 06-12-34-56-78
            # +33 6 12 34 56 78
            # +33612345678
            # 0033 6 12 34 56 78

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

            matches = re.findall(pattern, text)

            for match in matches:
                phone = normalize_phone(match)

                if phone:
                    return phone

    except Exception:
        pass

    return None


# ============================================================
# VERIFICATION DU SITE WEB
# ============================================================

async def has_website(page):
    """
    Vérifie si la fiche Google Maps possède un site web.
    """

    selectors = [
        'a[data-item-id="authority"]',
        'a[aria-label*="Site web"]',
        'a[aria-label*="site web"]',
        'a[aria-label*="Website"]',
        'a[aria-label*="website"]'
    ]

    for selector in selectors:
        try:
            if await page.locator(selector).count() > 0:
                return True
        except Exception:
            pass

    return False


# ============================================================
# EXTRACTION DU NOM
# ============================================================

async def extract_name(page):
    """
    Récupère le nom de l'entreprise depuis la fiche.
    """

    selectors = [
        'h1.DUwDvf',
        'h1.fontHeadlineLarge',
        'h1'
    ]

    for selector in selectors:
        try:
            element = page.locator(selector).first

            if await element.count() > 0:
                name = await element.inner_text()

                if name.strip():
                    return name.strip()

        except Exception:
            pass

    return "Inconnu"


# ============================================================
# OUVERTURE D'UNE FICHE
# ============================================================

async def scrape_business(
    page,
    maps_url,
    sector
):
    """
    Ouvre une fiche Google Maps et récupère :
    - nom
    - téléphone
    - présence d'un site
    - URL Google Maps
    """

    try:

        await page.goto(
            maps_url,
            wait_until="domcontentloaded",
            timeout=30000
        )

        # Laisser Google Maps charger les informations
        await asyncio.sleep(1.5)

        # ----------------------------------------------------
        # Nom
        # ----------------------------------------------------

        name = await extract_name(page)

        # ----------------------------------------------------
        # Site web
        # ----------------------------------------------------

        website = await has_website(page)

        if website:
            print(f"       🌐 {name} -> possède un site")
            return None

        # ----------------------------------------------------
        # Téléphone
        # ----------------------------------------------------

        phone = await extract_phone(page)

        if phone:
            print(f"       📞 {name} -> {phone}")
        else:
            print(f"       ⚠️ {name} -> téléphone introuvable")

        # ----------------------------------------------------
        # Résultat
        # ----------------------------------------------------

        return {
            "Secteur": sector,
            "Nom": name,
            "Téléphone": phone if phone else "Non spécifié",
            "Ville": CITY,
            "Lien Google Maps": maps_url
        }

    except Exception as e:

        print(
            f"       ❌ Erreur ouverture fiche : {e}"
        )

        return None


# ============================================================
# SCRAPING D'UN SECTEUR
# ============================================================

async def scrape_sector(
    page,
    query,
    sector,
    max_results
):

    print()
    print("=" * 60)
    print(f"🔍 Recherche : {query}")
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
            f"❌ Erreur de chargement pour {query}: {e}"
        )

        return []

    # --------------------------------------------------------
    # Attendre les résultats
    # --------------------------------------------------------

    try:

        await page.wait_for_selector(
            'div[role="feed"]',
            timeout=10000
        )

    except Exception:

        print(
            f"⚠️ Aucun résultat trouvé pour {query}"
        )

        return []

    # --------------------------------------------------------
    # Scroll des résultats
    # --------------------------------------------------------

    for _ in range(max_results // 5 + 2):

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

        await asyncio.sleep(1)

    # --------------------------------------------------------
    # Récupération des cartes
    # --------------------------------------------------------

    cards = await page.locator(
        'div[role="article"]'
    ).all()

    print(
        f"📋 {len(cards)} résultats trouvés"
    )

    # --------------------------------------------------------
    # Récupération des URLs AVANT d'ouvrir les fiches
    # --------------------------------------------------------

    businesses = []

    for card in cards[:max_results]:

        try:

            # URL Google Maps
            link = card.locator(
                'a[href*="/maps/place/"]'
            ).first

            if await link.count() == 0:
                continue

            maps_url = await link.get_attribute("href")

            if not maps_url:
                continue

            # Nom approximatif depuis la carte
            title = card.locator(
                'div.qBF1Pd'
            ).first

            if await title.count() > 0:
                name = (
                    await title.inner_text()
                ).strip()
            else:
                name = "Inconnu"

            businesses.append({
                "name": name,
                "url": maps_url
            })

        except Exception:
            continue

    print(
        f"📋 {len(businesses)} fiches à vérifier"
    )

    # --------------------------------------------------------
    # Ouverture de chaque fiche
    # --------------------------------------------------------

    sector_leads = []

    for index, business in enumerate(
        businesses,
        start=1
    ):

        print(
            f"\n[{index}/{len(businesses)}] "
            f"{business['name']}"
        )

        result = await scrape_business(
            page,
            business["url"],
            sector
        )

        if result:

            sector_leads.append(
                result
            )

        # Petite pause pour éviter
        # d'enchaîner trop rapidement
        await asyncio.sleep(1)

    print()
    print(
        f"✅ {len(sector_leads)} prospects "
        f"sans site pour {sector}"
    )

    return sector_leads


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

async def main():

    all_leads = []

    async with async_playwright() as p:

        # ----------------------------------------------------
        # Navigateur
        # ----------------------------------------------------

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

            locale="fr-FR"
        )

        page = await context.new_page()

        # ----------------------------------------------------
        # Cookies Google
        # ----------------------------------------------------

        first_query = (
            f"{BUSINESS_TYPES[0]} {CITY}"
        )

        try:

            await page.goto(
                "https://www.google.com/maps/search/"
                + first_query.replace(" ", "+"),
                wait_until="domcontentloaded",
                timeout=30000
            )

            await asyncio.sleep(1)

            cookie_buttons = page.locator(
                "button:has-text('Tout accepter'), "
                "button:has-text('Accept all'), "
                "button:has-text('Tout refuser')"
            )

            if await cookie_buttons.count() > 0:

                try:
                    await cookie_buttons.first.click(
                        timeout=4000
                    )

                    await asyncio.sleep(1)

                except Exception:
                    pass

        except Exception as e:

            print(
                f"Erreur initialisation Google Maps : {e}"
            )

        # ----------------------------------------------------
        # Boucle sur les secteurs
        # ----------------------------------------------------

        for business_type in BUSINESS_TYPES:

            query = (
                f"{business_type} {CITY}"
            )

            leads = await scrape_sector(
                page,
                query,
                business_type,
                MAX_RESULTS_PER_TYPE
            )

            all_leads.extend(leads)

            # Pause entre les recherches
            await asyncio.sleep(2)

        # ----------------------------------------------------
        # Fermeture navigateur
        # ----------------------------------------------------

        await browser.close()

    # ========================================================
    # TRAITEMENT DES DONNÉES
    # ========================================================

    if not all_leads:

        print()
        print(
            "❌ Aucun prospect trouvé."
        )

        return

    df = pd.DataFrame(
        all_leads
    )

    # --------------------------------------------------------
    # Nettoyage des téléphones
    # --------------------------------------------------------

    df["Téléphone"] = df[
        "Téléphone"
    ].apply(
        lambda x: (
            normalize_phone(x)
            if x != "Non spécifié"
            else "Non spécifié"
        )
    )

    # --------------------------------------------------------
    # Suppression des doublons
    # --------------------------------------------------------

    df = df.drop_duplicates(
        subset=[
            "Nom",
            "Téléphone"
        ]
    )

    # --------------------------------------------------------
    # Tri
    # --------------------------------------------------------

    df = df.sort_values(
        by=[
            "Secteur",
            "Nom"
        ]
    )

    # --------------------------------------------------------
    # Export CSV
    # --------------------------------------------------------

    df.to_csv(
        OUTPUT_FILENAME,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # STATISTIQUES
    # ========================================================

    total = len(df)

    with_phone = len(
        df[
            df["Téléphone"]
            != "Non spécifié"
        ]
    )

    without_phone = total - with_phone

    print()
    print("=" * 60)
    print("🎉 SCRAPING TERMINÉ")
    print("=" * 60)

    print(
        f"📊 Total prospects : {total}"
    )

    print(
        f"📞 Avec téléphone : {with_phone}"
    )

    print(
        f"⚠️ Sans téléphone : {without_phone}"
    )

    print(
        f"📁 Fichier : {OUTPUT_FILENAME}"
    )

    print("=" * 60)


# ============================================================
# LANCEMENT
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())
