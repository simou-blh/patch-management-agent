# Projet Plateforme d'Agents : Reference complete

> Ce fichier regroupe, en un seul endroit, **tout le contenu** des documents fournis par l'enseignant :
> noyau (README), contrat d'integration, registre inter-agents, guide du developpeur, agent exemple (README, `main.py`, manifeste, Dockerfile, requirements) et le `requirements.txt` du noyau.
> Le contenu original (en francais) est conserve tel quel. Les sections 0 et 12 sont des ajouts de synthese.

---

## Table des matieres

0. [Vue d'ensemble et organisation du depot](#0-vue-densemble-et-organisation-du-depot)
1. [Noyau de la plateforme (README_NOYAU)](#1-noyau-de-la-plateforme-readme_noyau)
2. [Contrat d'integration des agents (AGENT_INTEGRATION_CONTRACT)](#2-contrat-dintegration-des-agents-agent_integration_contract)
3. [Registre des objets partages (INTER_AGENT_DATA_CONTRACT)](#3-registre-des-objets-partages-inter_agent_data_contract)
4. [Guide du developpeur d'agent (DEVELOPER_INSTRUCTIONS)](#4-guide-du-developpeur-dagent-developer_instructions)
5. [Agent exemple : README](#5-agent-exemple--readme)
6. [Agent exemple : main.py](#6-agent-exemple--mainpy)
7. [Agent exemple : agent.manifest.json](#7-agent-exemple--agentmanifestjson)
8. [Agent exemple : Dockerfile](#8-agent-exemple--dockerfile)
9. [Agent exemple : requirements.txt](#9-agent-exemple--requirementstxt)
10. [Noyau : requirements.txt](#10-noyau--requirementstxt)
11. [Capture d'ecran du dossier du projet](#11-capture-decran-du-dossier-du-projet)
12. [Points d'attention et checklist](#12-points-dattention-et-checklist)

---

## 0. Vue d'ensemble et organisation du depot

### Architecture en un coup d'oeil

```
        +-------------------------------+
        |   NOYAU (fourni, NON modifie) |
        |  FastAPI + PostgreSQL :8000   |
        |  auth, catalogue, souscription|
        |  agent gateway, bus d'echange |
        +---------------+---------------+
                        |  HTTP/JSON (enveloppe standard)
      +-----------------+------------------+
      |                 |                  |
+-----v------+   +------v------+   +-------v-----+
| Agent      |   | Agent       |   | Agent       |
| Cybersec.  |   | Automat.    |   | IoT         |
| (Docker)   |   | metier      |   | (Docker)    |
+------------+   +-------------+   +-------------+
  Chaque agent = service independant, son propre conteneur.
  Les agents ne s'appellent JAMAIS entre eux : tout passe par le bus du noyau.
```

### Structure du dossier racine (d'apres la capture d'ecran)

```
Noyau_Conduite projet version 1/
├── agent-exemple/      <- gabarit d'agent (a copier pour votre propre agent)
├── app/                <- code du noyau (ne pas modifier)
├── scripts/            <- create_admin.py
└── requirements.txt    <- dependances du noyau
```

### Structure detaillee du noyau (d'apres README_NOYAU)

```
app/
  main.py              point d'entree de l'application
  database.py          connexion a la base de donnees
  models.py            tables (Company, User, Agent, AgentSubscription, ...)
  core/
    security.py        authentification (JWT, cookies, mots de passe)
    agent_gateway.py   appels sortants du noyau vers un agent
    exchange_bus.py    bus d'echange de donnees inter-agents
  routers/
    auth.py, companies.py, agents.py, subscriptions.py, admin.py,
    webhooks.py, exchange.py      routes API (JSON)
    pages.py                      pages web (HTML)
  templates/            pages HTML (Jinja2)
  static/               feuille de style
scripts/
  create_admin.py       creation du compte administrateur
agent-exemple/
  main.py, agent.manifest.json, Dockerfile, requirements.txt
```

### Structure recommandee pour le depot de VOTRE agent

(Deduite de l'etape 0 du guide : `cp -r agent-exemple mon-agent`)

```
mon-agent/
├── main.py                 <- 5 endpoints obligatoires + votre logique metier
├── agent.manifest.json     <- a la RACINE du depot (exige par le contrat)
├── Dockerfile              <- fonctionnel et autonome
├── requirements.txt        <- dependances de l'agent uniquement
└── README (optionnel)
```

### Cycle de vie d'un agent

```
Developpement  ->  POST /agents/submit  ->  statut "soumis"
      ->  verification par l'admin (/admin)  ->  certification + publication
      ->  visible dans /catalogue  ->  souscription par une entreprise
      ->  le noyau appelle POST /tenant/activate sur l'agent
```

---

## 1. Noyau de la plateforme (README_NOYAU)

**Noyau de la plateforme**

*Presentation generale et prise en main*

### Objet de ce document

Ce document decrit le noyau commun aux trois filieres du mini-projet (cybersecurite, automatisation metier, IoT). Le noyau est fourni par l'enseignant et ne doit pas etre modifie par les equipes etudiantes : il contient tout ce qui est necessaire pour faire fonctionner la plateforme, a l'exception des agents eux-memes, qui sont le livrable de chaque equipe.

### Ce que contient le noyau

- L'inscription et l'authentification des entreprises clientes (multi-tenant).
- Un catalogue d'agents, avec soumission, verification et publication par l'administrateur.
- La souscription d'une entreprise a un ou plusieurs agents, avec activation reelle aupres de l'agent.
- Une passerelle d'integration (agent gateway) qui controle que chaque agent respecte le contrat.
- Un bus d'echange de donnees inter-agents, utilisable par les agents qui en ont besoin.
- Trois interfaces web : inscription/catalogue pour les entreprises, tableau de bord entreprise, et back-office pour l'administrateur (l'enseignant).
- Un agent exemple, a utiliser comme point de depart pour developper votre propre agent.

### Ce que le noyau NE contient PAS

Le noyau ne contient aucune logique metier d'agent. C'est volontaire : chaque equipe developpe son agent comme un service independant, qui ne communique avec le noyau qu'a travers les regles decrites dans AGENT_INTEGRATION_CONTRACT.docx.

### Installation

```bash
pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg2://saas_user:saas_pass@localhost:5432/plateforme_agents"
export JWT_SECRET_KEY="une-cle-longue-et-aleatoire"
uvicorn app.main:app --reload --port 8000
```

Au premier lancement, creez le compte administrateur (l'enseignant) avec le script fourni :

```bash
python scripts/create_admin.py
```

La documentation interactive de l'API est accessible sur http://localhost:8000/docs. Les pages web sont accessibles sur http://localhost:8000/ (accueil), /inscription, /connexion, /catalogue, /mon-compte et /admin.

### Organisation du code

```
app/
  main.py              point d'entree de l'application
  database.py          connexion a la base de donnees
  models.py            tables (Company, User, Agent, AgentSubscription, ...)
  core/
    security.py        authentification (JWT, cookies, mots de passe)
    agent_gateway.py    appels sortants du noyau vers un agent
    exchange_bus.py     bus d'echange de donnees inter-agents
  routers/
    auth.py, companies.py, agents.py, subscriptions.py, admin.py,
    webhooks.py, exchange.py      routes API (JSON)
    pages.py                      pages web (HTML)
  templates/            pages HTML (Jinja2)
  static/               feuille de style
scripts/
  create_admin.py       creation du compte administrateur
agent-exemple/
  main.py, agent.manifest.json, Dockerfile, requirements.txt
```

### Le parcours d'un agent, de la soumission a la publication

1. L'equipe developpe son agent en suivant AGENT_INTEGRATION_CONTRACT.docx et DEVELOPER_INSTRUCTIONS.docx.
2. Elle le soumet avec POST /agents/submit (voir DEVELOPER_INSTRUCTIONS.docx). L'agent entre en statut "soumis".
3. L'administrateur verifie sa conformite depuis la page /admin, puis le certifie et le publie.
4. L'agent apparait dans le catalogue (/catalogue) et peut etre souscrit par une entreprise.
5. A la souscription, le noyau appelle automatiquement l'agent pour l'activer. Si l'agent ne repond pas correctement (voir l'enveloppe de reponse standard du contrat), la souscription reste en erreur plutot que de planter la plateforme.

### Documents associes

- AGENT_INTEGRATION_CONTRACT.docx : le contrat technique que chaque agent doit respecter.
- INTER_AGENT_DATA_CONTRACT.docx : le registre des objets partages pour les agents qui collaborent entre eux.
- DEVELOPER_INSTRUCTIONS.docx : le guide pas-a-pas pour developper et soumettre un agent.
- GUIDE_GITHUB_NOYAU.docx : comment publier ce noyau sur GitHub et organiser les depots des equipes. *(non fourni pour l'instant)*

---

## 2. Contrat d'integration des agents (AGENT_INTEGRATION_CONTRACT)

**Contrat d'integration des agents**

*Document de reference, commun aux trois filieres*

**Version du contrat : 1.0, applicable aux filieres Cybersecurite, Automatisation metier et IoT.**

Ce document decrit precisement comment un agent, quelle que soit l'equipe qui le developpe, doit communiquer avec le noyau pour pouvoir y etre integre. Un agent qui ne le respecte pas sera refuse lors de la verification par l'enseignant, ou suspendu s'il est deja publie.

### 1. Principe general

Chaque agent est un programme independant, qui expose une API HTTP, et qui tourne separement du noyau (en pratique, dans son propre conteneur Docker). Le noyau ne lit jamais directement le code ou la base de donnees d'un agent : il ne connait de lui que son adresse (base_url) et son manifeste.

- Un agent ne doit jamais appeler directement l'adresse d'un autre agent. Toute collaboration passe par le bus d'echange du noyau (section 6).
- Un agent recoit systematiquement l'identifiant de l'entreprise concernee (X-Tenant-Id) et sa cle d'acces (tenant_api_key) a chaque appel : il ne doit jamais deviner lui-meme quelle entreprise l'appelle.

### 2. Le fichier manifeste (agent.manifest.json)

Chaque agent fournit, a la racine de son depot, un fichier manifeste conforme a l'exemple suivant (reprenez le fichier agent.manifest.json de l'agent exemple et modifiez-le) :

```json
{
  "slug": "mon-agent",
  "name": "Nom de mon agent",
  "version": "1.0.0",
  "description": "Description courte",
  "filiere": "cybersecurite",
  "category": "scan",
  "developer": { "name": "...", "email": "..." },
  "team_name": "Equipe 3",
  "pricing_model": "flat_monthly",
  "price": 0,
  "endpoints": {
    "base_url": "http://mon-agent:8080",
    "health": "/health",
    "activate": "/tenant/activate",
    "deactivate": "/tenant/deactivate",
    "status": "/tenant/{tenant_id}/status",
    "config_schema": "/config-schema",
    "exchange_notify": "/exchange/notify"
  },
  "produces": [],
  "consumes": []
}
```

Le champ filiere accepte exactement trois valeurs : `cybersecurite`, `automatisation_metier`, `iot`. Les champs produces et consumes restent vides par defaut : ils ne sont a remplir que si votre agent echange des donnees avec un autre agent (voir section 6). Un agent qui se contente d'envoyer des alertes n'en a pas besoin.

### 3. Les 5 endpoints obligatoires

**GET /health**

```
Reponse : { "status": "ok", "data": { "uptime_seconds": 1234 }, "error": null }
```

**POST /tenant/activate**

Appele par le noyau quand une entreprise souscrit a l'agent.

```
Requete recue :
  Headers : Authorization: Bearer <tenant_api_key>
            X-Tenant-Id: <company_id>
  Corps   : { "config": { ... } }
Reponse  : { "status": "ok", "data": { "activated": true }, "error": null }
```

**POST /tenant/deactivate**

Doit supprimer ou anonymiser les donnees du tenant concerne.

```
Reponse : { "status": "ok", "data": { "deactivated": true, "data_purged": true }, "error": null }
```

**GET /tenant/{tenant_id}/status**

```
Reponse : { "status": "ok", "data": { "state": "running" }, "error": null }
```

**GET /config-schema**

Decrit en JSON Schema les parametres que l'entreprise peut renseigner a l'activation.

### 4. L'enveloppe de reponse standard

Toute reponse HTTP d'un agent, sur tout endpoint, doit respecter cette structure exacte :

```json
{ "status": "ok" | "error", "data": { ... } | null, "error": "message" | null }
```

Une reponse qui ne la respecte pas est traitee par le noyau comme une violation du contrat, ce qui suspend automatiquement la souscription concernee.

### 5. Le webhook d'alertes

Un agent peut signaler un evenement (alerte, notification) au noyau a tout moment :

```
POST /webhooks/agent-events
Headers : Authorization: Bearer <tenant_api_key>
          X-Tenant-Id: <company_id>
Corps   : { "event_type": "...", "severity": "info|low|medium|high|critical", "data": { ... } }
```

C'est le mecanisme le plus simple, suffisant pour la grande majorite des agents des filieres cybersecurite et IoT : un scanner de vulnerabilites, un capteur de temperature ou un systeme de detection d'intrusion n'ont besoin que de ce canal pour remplir leur role.

### 6. Le bus d'echange (optionnel, pour les agents qui collaborent)

Certains agents doivent echanger des donnees entre eux, en particulier dans la filiere automatisation metier (un agent Logistique a besoin de connaitre le stock avant de programmer une expedition). Le mecanisme est decrit en detail dans INTER_AGENT_DATA_CONTRACT.docx ; en resume :

- Un agent publie un objet avec POST /exchange/agent/{type}. Il doit avoir declare ce type dans son champ produces.
- Le noyau notifie automatiquement, via POST sur l'endpoint exchange_notify de chaque agent concerne, tout agent actif de la meme entreprise qui declare consommer ce type dans son champ consumes.
- Un humain de l'entreprise peut alimenter ou consulter les memes objets depuis son tableau de bord, meme si elle n'a souscrit a aucun agent correspondant.

Un agent qui n'a pas besoin de ce mecanisme laisse simplement produces et consumes vides dans son manifeste, et n'implemente pas /exchange/notify.

### 7. Securite et isolation des donnees

- Isolation stricte par tenant : aucune donnee d'une entreprise ne doit etre visible par une autre.
- Aucun secret en dur dans le code (utilisez des variables d'environnement).
- POST /tenant/deactivate doit reellement supprimer les donnees du tenant.
- Aucun appel reseau vers un service non mentionne dans votre rapport d'execution.

### 8. Packaging

Chaque agent est livre avec un Dockerfile fonctionnel et autonome (voir celui de l'agent exemple). Le port d'ecoute doit correspondre a celui declare dans base_url.

### 9. Verification avant publication

Avant de certifier un agent, l'enseignant verifie :

- Le manifeste est valide et le slug est unique.
- Les 5 endpoints obligatoires repondent avec l'enveloppe standard.
- L'agent s'active et se desactive correctement depuis la page /admin.
- Si consumes n'est pas vide, /exchange/notify fonctionne avec un objet de test.
- Aucune fuite de donnees entre deux tenants de test.

### 10. Repartition des responsabilites

|  | **Noyau (enseignant)** | **Agent (equipe etudiante)** |
| --- | --- | --- |
| Authentification, entreprises, catalogue | Oui | Non |
| Bus d'echange (stockage, routage) | Oui | Produit/consomme uniquement |
| Logique metier de l'agent | Non | Oui |
| Isolation des donnees du tenant | Verifie | Implemente |
| Disponibilite de l'agent pendant la demo | Non | Oui |

---

## 3. Registre des objets partages (INTER_AGENT_DATA_CONTRACT)

**Registre des objets partages**

*Bus d'echange inter-agents, document commun a toutes les equipes*

Ce document liste les types d'objets que les agents peuvent produire ou consommer via le bus d'echange du noyau (voir AGENT_INTEGRATION_CONTRACT.docx, section 6). Il concerne surtout la filiere automatisation metier, mais rien n'empeche un agent IoT ou cybersecurite de produire un objet reutilisable par un autre agent (par exemple, un capteur de stock connecte peut produire le meme objet stock_level qu'un agent logiciel classique).

Si votre agent a besoin d'un type d'objet qui n'est pas dans ce registre, ouvrez une issue sur le depot GitHub du noyau pour en proposer l'ajout plutot que de l'inventer seul : c'est ce document, partage par toutes les equipes, qui garantit que deux agents developpes separement se comprennent.

### Exemple de chaine de dependances (filiere automatisation metier)

```
Agent Commercial --produit--> commande
                                  |
                                  v (consomme par)
Agent Stock --consomme-- commande --produit--> stock_level, mouvement_stock
                                                        |
                                                        v
Agent Logistique --consomme-- stock_level, commande --produit--> expedition
                                                                        |
                                                                        v
Agent Facturation --consomme-- commande, expedition --produit--> facture
```

Une entreprise peut ne souscrire qu'a certains de ces agents : l'objet manquant peut alors etre saisi manuellement par un employe depuis le tableau de bord.

### 1. commande

```json
{
  "numero_commande": "CMD-2027-0001",
  "date_commande": "2027-01-10T10:00:00Z",
  "client": { "nom": "Societe Dupont", "email": "contact@dupont.fr" },
  "lignes": [{ "sku": "SKU-001", "quantite": 10, "prix_unitaire_ht": 4.50 }],
  "montant_total_ht": 45.00,
  "statut": "en_attente"
}
```

statut : en_attente, confirmee, expediee, facturee, annulee.

### 2. stock_level

```json
{
  "sku": "SKU-001",
  "designation": "Cable HDMI 2m",
  "quantite_disponible": 42,
  "seuil_alerte": 10,
  "entrepot": "Entrepot Nord"
}
```

Peut etre produit par un agent logiciel de gestion de stock, ou directement par un agent IoT de pesee connectee : les deux publient le meme type d'objet.

### 3. mouvement_stock

```json
{
  "id_mouvement": "MVT-2027-0456",
  "sku": "SKU-001",
  "type_mouvement": "sortie",
  "quantite": 10,
  "reference_commande": "CMD-2027-0001"
}
```

type_mouvement : entree, sortie, ajustement.

### 4. expedition

```json
{
  "numero_expedition": "EXP-2027-0089",
  "reference_commande": "CMD-2027-0001",
  "transporteur": "Colissimo",
  "numero_suivi": "6A12345678901",
  "statut": "en_transit"
}
```

statut : preparation, en_transit, livree, retour.

### 5. facture

```json
{
  "numero_facture": "FAC-2027-0033",
  "reference_commande": "CMD-2027-0001",
  "montant_total_ttc": 54.00,
  "statut_paiement": "en_attente"
}
```

statut_paiement : en_attente, payee, en_retard, annulee.

### 6. prospect

```json
{
  "id_prospect": "PROS-2027-0210",
  "nom": "Martin Leroy",
  "email": "martin.leroy@example.com",
  "score_interet": 72,
  "statut": "qualifie"
}
```

### 7. ticket_support

```json
{
  "id_ticket": "TCK-2027-0077",
  "sujet": "Retard de livraison",
  "reference_commande": "CMD-2027-0001",
  "priorite": "moyenne",
  "statut": "ouvert"
}
```

### 8. mesure_capteur (filiere IoT)

Permet a un agent IoT de partager une lecture de capteur avec un autre agent (par exemple un agent de reporting qui agrege plusieurs sources).

```json
{
  "capteur_id": "TEMP-ENTREPOT-03",
  "type_mesure": "temperature",
  "valeur": 6.2,
  "unite": "celsius",
  "horodatage": "2027-01-10T10:00:00Z"
}
```

### Regles communes

- L'identifiant metier (external_id) correspond au champ "numero" ou "id" naturel de l'objet.
- Les dates sont au format ISO 8601, en UTC.
- Un champ inconnu recu par un agent doit etre ignore silencieusement, jamais provoquer une erreur : cela permet de faire evoluer un objet sans casser les agents existants.
- La suppression ou le renommage d'un champ obligatoire necessite une validation prealable par l'enseignant.

### Proposer un nouveau type d'objet

Ouvrez une issue sur le depot GitHub du noyau avec le schema propose et la liste des agents concernes. Une fois validee, la description est ajoutee a ce document et devient utilisable par toutes les equipes.

---

## 4. Guide du developpeur d'agent (DEVELOPER_INSTRUCTIONS)

**Guide du developpeur d'agent**

*Comment construire, tester et soumettre votre agent*

Ce guide s'adresse a chaque equipe etudiante, quelle que soit sa filiere. Il part du principe que vous avez deja lu AGENT_INTEGRATION_CONTRACT.docx et, si votre agent echange des donnees avec un autre agent, INTER_AGENT_DATA_CONTRACT.docx.

### Etape 0 : Partir de l'agent exemple

Le noyau est livre avec un dossier agent-exemple/, qui contient un agent minimal mais complet : les 5 endpoints obligatoires, un endpoint exchange/notify de demonstration, un manifeste, un Dockerfile. Copiez ce dossier pour demarrer votre propre agent plutot que de repartir de zero.

```bash
cp -r agent-exemple mon-agent
cd mon-agent
```

### Etape 1 : Choisir votre stack technique

Meme si le noyau n'impose aucun langage : Python, Node.js, Go, Java... du moment que votre agent expose une API HTTP/JSON conforme au contrat. **Cependant, pour une meilleure coherence du projet, le langage Python doit etre utilise.** Par ailleurs, l'agent exemple est ecrit en Python/FastAPI ce qui est rapide a prendre en main.

### Etape 2 : Adapter le manifeste

Modifiez agent.manifest.json : slug, name, description, filiere, category, developer, team_name. Laissez produces et consumes vides si votre agent n'echange pas de donnees avec un autre agent.

### Etape 3 : Developper votre logique metier

Remplacez le code de demonstration de main.py par le comportement reel de votre agent, en respectant les regles de base :

- Filtrez toujours vos donnees par tenant_id.
- N'appelez jamais directement l'adresse d'un autre agent : passez par le bus d'echange du noyau si necessaire.
- Ne loggez jamais de donnees sensibles en clair.

### Etape 4 : Envoyer une alerte (si besoin)

```bash
curl -X POST http://localhost:8000/webhooks/agent-events \
  -H "Authorization: Bearer <tenant_api_key>" \
  -H "X-Tenant-Id: <company_id>" \
  -H "Content-Type: application/json" \
  -d '{"event_type": "seuil_depasse", "severity": "medium", "data": {"valeur": 95}}'
```

### Etape 5 : Publier et recevoir des objets (selon le besoin)

Si votre agent produit un objet :

```bash
curl -X POST http://localhost:8000/exchange/agent/stock_level \
  -H "Authorization: Bearer <tenant_api_key>" \
  -H "X-Tenant-Id: <company_id>" \
  -d '{"external_id": "SKU-001", "payload": {"quantite_disponible": 37}}'
```

Si votre agent consomme un objet, implementez /exchange/notify (deja present dans l'agent exemple) : le noyau l'appellera automatiquement des qu'un objet du type concerne est publie par un autre agent, ou par un humain depuis le tableau de bord.

### Etape 6 : Conteneuriser

Adaptez le Dockerfile fourni si votre stack differe de Python. Verifiez que l'image demarre sans configuration manuelle autre que les variables d'environnement.

### Etape 7 : Tester en local avant de soumettre

Lancez le noyau et votre agent en parallele, puis simulez vous-meme : inscription d'une entreprise de test (page /inscription), souscription a votre agent une fois publie (voir etape 9), activation, et si applicable, publication/reception d'un objet de test.

### Etape 8 : Soumettre votre agent

```bash
curl -X POST http://localhost:8000/agents/submit \
  -H "Content-Type: application/json" \
  -d @agent.manifest.json
```

Votre agent passe en statut "soumis". L'enseignant le verifie depuis la page /admin.

### Etape 9 : Certification et publication

Une fois verifie conforme, l'enseignant certifie puis publie votre agent depuis /admin. Il apparait alors dans le catalogue (/catalogue) et devient souscriptible par une entreprise de test ou de demonstration.

### Liste de verification avant de soumettre

- Les 5 endpoints obligatoires repondent avec l'enveloppe standard {status, data, error}.
- Le manifeste est valide, le slug unique, la filiere renseignee.
- Isolation par tenant_id verifiee manuellement (deux entreprises de test ne se voient jamais).
- Le Dockerfile fonctionne (docker build puis docker run).
- POST /tenant/deactivate supprime reellement les donnees de test.
- Si consumes n'est pas vide : /exchange/notify a ete teste avec un objet factice.

---

## 5. Agent exemple : README

**Agent exemple**

*Gabarit de depart pour votre propre agent*

Ce dossier n'est pas un agent utile en lui-meme : c'est un squelette minimal mais complet, qui respecte deja AGENT_INTEGRATION_CONTRACT.docx. Copiez-le et remplacez la logique de demonstration par le comportement reel de votre agent.

### Contenu du dossier

- main.py : les 5 endpoints obligatoires, plus un exemple d'envoi d'alerte et de reception d'un objet du bus d'echange.
- agent.manifest.json : le manifeste a adapter (slug, nom, filiere, equipe...).
- Dockerfile : pret a l'emploi pour une stack Python ; a reecrire si vous changez de langage.
- requirements.txt : dependances minimales.

### Lancer l'agent exemple en local

```bash
pip install -r requirements.txt
uvicorn main:app --port 9000
```

Variable d'environnement NOYAU_URL : adresse du noyau, utilisee pour l'envoi des alertes (par defaut http://localhost:8000).

### Tester manuellement le scenario de demonstration

Une fois votre entreprise de test inscrite et l'agent exemple souscrit depuis /catalogue, simulez l'arrivee d'une mesure :

```bash
curl -X POST "http://localhost:9000/demo/mesure/<tenant_id>?valeur=95"
```

Si la valeur depasse le seuil configure (80 par defaut), une alerte est automatiquement envoyee au noyau et apparait dans le tableau de bord de l'entreprise (/mon-compte).

### Ce qu'il faut remplacer pour en faire votre agent

- La section "LOGIQUE DE DEMONSTRATION" de main.py, par votre propre traitement.
- Le contenu de agent.manifest.json.
- Les dependances de requirements.txt selon ce dont votre agent a reellement besoin.
- Les champs produces/consumes si votre agent echange des objets avec un autre (voir INTER_AGENT_DATA_CONTRACT.docx).

---

## 6. Agent exemple : main.py

Fichier : `agent-exemple/main.py`

```python
"""
Agent exemple.

Ce fichier n'est pas un agent "utile" en soi : c'est un gabarit minimal,
qui respecte le contrat d'integration du noyau, et qui sert de point de
depart pour chaque equipe. Les 6 routes ci-dessous sont celles exigees
par AGENT_INTEGRATION_CONTRACT.docx ; tout le reste (la logique metier
reelle de votre agent) est a ecrire a la place du code de demonstration
que vous trouverez dans la section "LOGIQUE DE DEMONSTRATION" plus bas.

Pour lancer cet agent en local :
    pip install -r requirements.txt
    uvicorn main:app --port 9000

Il faudra ensuite le soumettre au noyau avec le fichier agent.manifest.json
fourni a cote de ce main.py (voir DEVELOPER_INSTRUCTIONS.docx, etape 10).
"""
import os
import time
import httpx
from fastapi import FastAPI, Header, HTTPException

app = FastAPI(title="Agent exemple")

# Stockage en memoire, par tenant. Pour un vrai agent, remplacez ceci par
# une vraie base de donnees (SQLite suffit largement pour ce mini-projet).
etat_par_tenant: dict[str, dict] = {}

demarre_le = time.time()

NOYAU_URL = os.getenv("NOYAU_URL", "http://localhost:8000")


# ---------------------------------------------------------------------
# Les 5 routes obligatoires du contrat
# ---------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "data": {"uptime_seconds": int(time.time() - demarre_le)},
        "error": None,
    }


@app.post("/tenant/activate")
def activate(body: dict, authorization: str = Header(None), x_tenant_id: str = Header(None, alias="X-Tenant-Id")):
    if not x_tenant_id:
        raise HTTPException(400, "X-Tenant-Id manquant")

    config = body.get("config", {})
    etat_par_tenant[x_tenant_id] = {
        "tenant_api_key": authorization.replace("Bearer ", "") if authorization else None,
        "config": config,
        "seuil_alerte": config.get("seuil_alerte", 80),
        "derniere_mesure": None,
    }
    return {"status": "ok", "data": {"activated": True}, "error": None}


@app.post("/tenant/deactivate")
def deactivate(x_tenant_id: str = Header(None, alias="X-Tenant-Id")):
    etat_par_tenant.pop(x_tenant_id, None)
    return {"status": "ok", "data": {"deactivated": True, "data_purged": True}, "error": None}


@app.get("/tenant/{tenant_id}/status")
def tenant_status(tenant_id: str):
    tenant = etat_par_tenant.get(tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant non active")
    return {
        "status": "ok",
        "data": {"state": "running", "derniere_mesure": tenant["derniere_mesure"]},
        "error": None,
    }


@app.get("/config-schema")
def config_schema():
    """
    Decrit les champs que l'entreprise peut renseigner a l'activation.
    Le noyau utilise ce schema pour generer le formulaire de configuration
    (dans une version future ; pour ce mini-projet, la config par defaut
    suffit).
    """
    return {
        "status": "ok",
        "data": {
            "type": "object",
            "properties": {
                "seuil_alerte": {
                    "type": "number",
                    "description": "Valeur au-dela de laquelle une alerte est envoyee",
                    "default": 80,
                }
            },
        },
        "error": None,
    }


# ---------------------------------------------------------------------
# Route facultative : a implementer uniquement si votre agent CONSOMME
# des objets du bus d'echange (champ "consumes" non vide dans votre
# manifeste). Sinon, vous pouvez supprimer cette fonction.
# ---------------------------------------------------------------------

@app.post("/exchange/notify")
def exchange_notify(body: dict, x_tenant_id: str = Header(None, alias="X-Tenant-Id")):
    # body contient : object_type, external_id, version, payload
    # Exemple : un agent de stock recevrait ici une "commande" publiee
    # par l'agent commercial, et deciderait quoi en faire.
    return {"status": "ok", "data": {"processed": True}, "error": None}


# ---------------------------------------------------------------------
# LOGIQUE DE DEMONSTRATION
#
# Ce qui suit n'est pas exige par le contrat : c'est un exemple concret
# pour montrer comment un agent envoie une alerte au noyau, et comment il
# peut, s'il le souhaite, publier un objet sur le bus d'echange. Une
# equipe de la filiere IoT pourrait remplacer "mesure" par une vraie
# lecture de capteur ; une equipe de la filiere cybersecurite par le
# resultat d'un scan ; etc.
# ---------------------------------------------------------------------

@app.post("/demo/mesure/{tenant_id}")
async def demo_recevoir_mesure(tenant_id: str, valeur: float):
    """
    Point d'entree de demonstration, appele ici manuellement (par exemple
    avec curl) pour simuler l'arrivee d'une mesure. Un vrai agent IoT
    appellerait ce genre de logique depuis une boucle de lecture de
    capteur, pas depuis une route HTTP exposee publiquement.
    """
    tenant = etat_par_tenant.get(tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant non active")

    tenant["derniere_mesure"] = valeur

    if valeur > tenant["seuil_alerte"]:
        await _envoyer_alerte(tenant_id, tenant["tenant_api_key"], valeur)

    return {"status": "ok", "data": {"recue": True}, "error": None}


async def _envoyer_alerte(tenant_id: str, tenant_api_key: str, valeur: float):
    """Exemple d'appel au webhook d'alertes du noyau."""
    async with httpx.AsyncClient(timeout=5) as client:
        await client.post(
            f"{NOYAU_URL}/webhooks/agent-events",
            headers={
                "Authorization": f"Bearer {tenant_api_key}",
                "X-Tenant-Id": tenant_id,
            },
            json={
                "event_type": "seuil_depasse",
                "severity": "medium",
                "data": {"valeur": valeur},
            },
        )
```

---

## 7. Agent exemple : agent.manifest.json

Fichier : `agent-exemple/agent.manifest.json`
*(le fichier a ete televerse sous le nom `agent_manifest.json`, mais le nom attendu par le contrat est `agent.manifest.json`)*

```json
{
  "slug": "agent-exemple",
  "name": "Agent exemple",
  "version": "1.0.0",
  "description": "Gabarit de reference, a utiliser comme point de depart pour developper votre propre agent.",
  "filiere": "iot",
  "category": "demonstration",
  "developer": {
    "name": "A completer",
    "email": "a-completer@etu.ecole.fr"
  },
  "team_name": "A completer",
  "pricing_model": "flat_monthly",
  "price": 0,
  "resource_requirements": {
    "cpu": "0.5",
    "memory_mb": 256
  },
  "endpoints": {
    "base_url": "http://localhost:9000",
    "health": "/health",
    "activate": "/tenant/activate",
    "deactivate": "/tenant/deactivate",
    "status": "/tenant/{tenant_id}/status",
    "config_schema": "/config-schema",
    "exchange_notify": "/exchange/notify"
  },
  "produces": [],
  "consumes": []
}
```

---

## 8. Agent exemple : Dockerfile

Fichier : `agent-exemple/Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 9000

HEALTHCHECK CMD python -c "import httpx; httpx.get('http://localhost:9000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
```

---

## 9. Agent exemple : requirements.txt

Fichier : `agent-exemple/requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
httpx==0.27.2
```

---

## 10. Noyau : requirements.txt

Fichier : `requirements.txt` (a la racine du noyau)

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy==2.0.35
psycopg2-binary==2.9.9
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
httpx==0.27.2
python-multipart==0.0.9
pydantic[email]==2.9.2
bcrypt==4.0.1
jinja2==3.1.4
```

---

## 11. Capture d'ecran du dossier du projet

Le dossier **`Noyau_Conduite projet version 1`** contient 4 elements :

| Nom | Type | Date de modification |
| --- | --- | --- |
| `agent-exemple` | Dossier | 10/23/2026 5:34 PM |
| `app` | Dossier | 10/23/2026 5:34 PM |
| `scripts` | Dossier | 10/23/2026 5:34 PM |
| `requirements` | Document texte (1 KB) | 10/7/2026 10:27 AM |

---

## 12. Points d'attention et checklist

*(Section de synthese ajoutee, ne fait pas partie des documents de l'enseignant.)*

### Incoherences et details a surveiller dans les documents fournis

1. **Port de l'agent** : le manifeste exemple declare `base_url: http://localhost:9000` et le Dockerfile expose `9000`, alors que le contrat montre `http://mon-agent:8080`. Regle : le port du Dockerfile doit correspondre a celui de `base_url`.
2. **"5 routes" vs "6 routes"** : le docstring de `main.py` parle de 6 routes, tandis que le contrat exige 5 endpoints obligatoires (`/exchange/notify` est facultatif).
3. **Reference a l'etape 10** : le docstring de `main.py` renvoie a "l'etape 10" du guide, mais le guide s'arrete a l'etape 9 (la soumission est l'etape 8).
4. **Nom du manifeste** : le fichier doit s'appeler `agent.manifest.json` (avec un point) et se trouver a la racine du depot de l'agent.
5. **Langage impose** : le guide dit que Python "doit etre utilise" pour la coherence du projet.
6. **Document manquant** : `GUIDE_GITHUB_NOYAU.docx` (publication du noyau sur GitHub et organisation des depots des equipes) n'a pas ete fourni.
7. **Code du noyau non fourni ici** : le contenu de `app/` et `scripts/` n'est pas dans les fichiers televerses (seulement visible comme dossiers dans la capture).
8. **Stockage de l'agent exemple** : en memoire (`etat_par_tenant`), donc perdu au redemarrage. SQLite est suggere pour un vrai agent.
9. **Champ `filiere`** : valeurs exactes `cybersecurite`, `automatisation_metier`, `iot`. L'agent exemple est declare en `iot`.

### Checklist avant soumission

- [ ] Les 5 endpoints obligatoires repondent avec l'enveloppe `{status, data, error}` (y compris pour les erreurs).
- [ ] Manifeste valide, slug unique, `filiere` renseignee, `base_url` coherent avec le port du Dockerfile.
- [ ] Isolation par `tenant_id` verifiee avec deux entreprises de test.
- [ ] `POST /tenant/deactivate` supprime reellement les donnees du tenant.
- [ ] `docker build` puis `docker run` fonctionnent sans configuration manuelle (hors variables d'environnement).
- [ ] Aucun secret en dur ; aucun appel reseau vers un service non declare dans le rapport d'execution.
- [ ] Aucun appel direct vers un autre agent (passer par le bus d'echange).
- [ ] Si `consumes` non vide : `/exchange/notify` teste avec un objet factice.
- [ ] Pas de donnees sensibles loggees en clair.
- [ ] Agent soumis via `POST /agents/submit`, puis verifie par l'enseignant sur `/admin`.

### Commandes utiles (aide-memoire)

```bash
# Noyau
pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg2://saas_user:saas_pass@localhost:5432/plateforme_agents"
export JWT_SECRET_KEY="une-cle-longue-et-aleatoire"
uvicorn app.main:app --reload --port 8000
python scripts/create_admin.py

# Agent
cp -r agent-exemple mon-agent && cd mon-agent
pip install -r requirements.txt
uvicorn main:app --port 9000
docker build -t mon-agent . && docker run -p 9000:9000 mon-agent

# Soumission
curl -X POST http://localhost:8000/agents/submit \
  -H "Content-Type: application/json" -d @agent.manifest.json
```

### URLs du noyau

| URL | Role |
| --- | --- |
| `http://localhost:8000/docs` | Documentation interactive de l'API |
| `/` | Accueil |
| `/inscription`, `/connexion` | Inscription / connexion des entreprises |
| `/catalogue` | Catalogue des agents publies |
| `/mon-compte` | Tableau de bord entreprise (alertes) |
| `/admin` | Back-office de l'enseignant |
