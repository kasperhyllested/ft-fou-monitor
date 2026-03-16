# FOU Monitor

Dette repo henter FOU-relaterede RSS-feeds fra Folketinget, vurderer hvert dokument med OpenAI API og bygger:

- en statisk webside på GitHub Pages
- et filtreret RSS-feed med kun score 4-5

## Hvad løsningen gør

Hver kørsel:
1. Henter de tre FOU-feeds
2. Finder nye dokumenter
3. Åbner dokumentlinket på ft.dk
4. Forsøger også at læse op til to tilknyttede PDF-filer
5. Sender tekst og metadata til OpenAI API
6. Gemmer score, ny overskrift, resumé og nøglefakta
7. Opdaterer webside og RSS-feed

## Før du går i gang

Du skal have:
- en GitHub-konto
- en OpenAI API-konto med betalingsmetode
- en OpenAI API-nøgle

## Step-by-step opsætning

### Del 1: Hent OpenAI API-nøgle

1. Åbn OpenAI platformen i browseren.
2. Log ind.
3. Gå til siden for API keys.
4. Opret en ny secret key.
5. Kopiér nøglen med det samme og gem den midlertidigt et sikkert sted.

### Del 2: Opret repository på GitHub

1. Log ind på GitHub.
2. Klik øverst til højre på **+**.
3. Klik **New repository**.
4. I feltet **Repository name** skriv `ft-fou-monitor`.
5. Vælg **Public**.
6. Sæt flueben i **Add a README file**.
7. Klik **Create repository**.

### Del 3: Upload filerne

1. Download filerne fra denne mappe eller upload dem manuelt til dit repo.
2. Du skal have disse filer og mapper i roden af repoet:

```text
.github/workflows/update.yml
scripts/update.py
requirements.txt
README.md
data/documents.json
data/seen_ids.json
site/index.html
site/feed.xml
site/.nojekyll
```

3. Hvis `data` og `site` ikke findes endnu, så opret mapperne i repoet.
4. Opret disse to filer med præcis dette indhold:

`data/documents.json`
```json
[]
```

`data/seen_ids.json`
```json
[]
```

5. Du må gerne lade `site/index.html` og `site/feed.xml` være tomme i starten. Workflowet overskriver dem.

### Del 4: Læg API-nøglen ind som GitHub Secret

1. Åbn dit repository.
2. Klik **Settings**.
3. I venstre side klik **Secrets and variables**.
4. Klik **Actions**.
5. Klik **New repository secret**.
6. I **Name** skriv `OPENAI_API_KEY`.
7. I **Secret** indsæt din OpenAI API-nøgle.
8. Klik **Add secret**.

### Del 5: Aktivér GitHub Pages

1. Gå til dit repository.
2. Klik **Settings**.
3. Klik **Pages** i venstre side.
4. Under **Build and deployment** vælg **Deploy from a branch**.
5. Under **Branch** vælg din hovedbranch, typisk `main`.
6. Vælg mappen `/site`.
7. Klik **Save**.

### Del 6: Start første kørsel manuelt

1. Gå til fanen **Actions**.
2. Klik workflowet **Update FOU monitor**.
3. Klik **Run workflow**.
4. Klik den grønne knap **Run workflow** igen.
5. Vent til jobbet er færdigt.
6. Klik på workflow-runnet og tjek at alle steps er grønne.

### Del 7: Find websiden og RSS-feedet

Når workflowet er kørt færdigt og GitHub Pages har publiceret siden, får du typisk:

- Webside: `https://DIT-BRUGERNAVN.github.io/ft-fou-monitor/`
- RSS-feed: `https://DIT-BRUGERNAVN.github.io/ft-fou-monitor/feed.xml`

Erstat `DIT-BRUGERNAVN` med dit GitHub-brugernavn.

## Hvordan tidsplanen virker

Workflowet kører automatisk på hverdage klokken:
- 06:15
- 10:15
- 14:15
- 18:15

Tiderne i cron-udtryk i GitHub Actions er i UTC. Du kan ændre schedule senere i `.github/workflows/update.yml`.

## Sådan ændrer du modellen

I workflowfilen står der:

```yaml
OPENAI_MODEL: gpt-5-mini
```

Du kan senere ændre modellen her, hvis du vil prioritere pris, hastighed eller kvalitet anderledes.

## Kendte begrænsninger

- Nogle Folketinget-dokumenter kan være svære at udtrække pænt, især hvis indholdet ligger dybt i PDF eller i dynamiske sider.
- Første prompt er bevidst konservativ, men bør justeres efter nogle dages brug.
- Hvis et workflow fejler på et enkelt dokument, fortsætter det med de øvrige.

## Næste forbedringer du kan tilføje senere

- mailnotifikation med kun nye score 5-dokumenter
- særskilt filter for virksomheder og kapaciteter
- bedre PDF-udtræk
- whitelist eller blacklist af emner
- eksport til CSV
