# AI Agent Implementation Spec: Recipe App (Raspberry Pi Deployment)

You are tasked with rebuilding this lightweight recipe management web application designed for local hosting on a Raspberry Pi. The system must prioritize simplicity, maintainability, and server-driven rendering. 

The existing app was built with limited skills and minimal AI. Any javascript should be havily scruitinized and probably replaced entirely.

I was also working in other branches (dev-phil and forms-branch) to try and change how the ORM works and update forms, but you need to fix this according to the instructions below.

## 1. Core Architecture

### Backend Framework
FastAPI is the primary backend framework.

Responsibilities:
- Handle HTTP routing (recipes, tags, search, meal planning)
- Process form submissions
- Serve HTML partials for dynamic UI updates
- Provide optional JSON endpoints only where necessary

### Database Layer
SQLAlchemy is used for all database interactions.

Responsibilities:
- Define models:
- Handle CRUD operations
- Maintain separation between models and business logic

### Database Migrations
Alembic is used for schema migrations.

Responsibilities:
- Track schema changes
- Provide version-controlled migrations
- Ensure safe database updates on Raspberry Pi deployment

---

## 2. Frontend Architecture

### Server Rendered UI with HTMX
HTMX handles:
- Type-ahead search inputs
- Partial page updates (recipes, filtering, sorting)
- Form submissions without full page reloads
- Dynamic updates to recipe cards and meal planning views

### Alpine.js for UI State
Alpine.js handles:
- Dropdown open/close behavior
- Multi-select tag inputs
- Lightweight UI state management

---

## 3. Application Features

### Recipe Management
- Create, edit, delete recipes
- Allow for bulk paste of ingredients and instructions 
- Multi-select UI via Alpine.js

### Ingredient Synonym System
- NOTE: The current synonyms page is just a placeholder. The template and data need to be added.
- Many-to-many relationship between recipes and ingredients
- Ability to add synonyms to ingredients that will allow them to be returned in search results

### Meal Planning
- Assign recipes to planned days

### Recipe Collections and Cuisines 
- Tag recipes to cuisines
- Tag recipes to one or more collections
- Create, edit and delete cuisines and collections 

### Search System
- Server-side search across:
  - title
  - ingredients
  - instructions
  - notes
- HTMX used for live search results and type-ahead

### User profiles (NEW)
- Secure user profile authentication
- User profiles manage their own recipes

---

## 4. Background Processing Constraint

No background job systems are used.

Explicitly avoid:
- Celery
- RQ
- Any async task queue

All operations must be synchronous and request-driven.

---

## 5. Infrastructure and Deployment

Containerize the existing FastAPI recipe application using Docker so it runs consistently on the Raspberry Pi. Use Docker Compose to manage the FastAPI service (running via Uvicorn) and connect it to the existing database setup. The current Nginx and related infrastructure already in place on the Pi may need to be updated to route traffic properly to the new containerized service.

### Containerization
Use Docker and Docker Compose where possible.
Do not use Docker for the database.

### Services
- FastAPI application container
- MariaDB (external or containerized)

### Application Server
Uvicorn runs the FastAPI application.

Responsibilities:
- Serve ASGI application inside container

### Reverse Proxy
Nginx is used as reverse proxy.

Responsibilities:
- Route traffic to FastAPI/Uvicorn
- Serve static assets if needed
- Optional TLS termination

### Raspberry Pi Requirements
- ARM-compatible containers
- Lightweight services only
- Single command deployment via docker-compose

---

## 6. System Design Principles

- No frontend frameworks (React, Vue, etc.)
- No microservices
- No distributed system complexity
- Minimal JavaScript usage
- Server handles most logic

Clear separation:
- FastAPI: routing and business logic
- SQLAlchemy: data layer
- HTMX: dynamic UI updates
- Alpine.js: UI state
- Nginx: reverse proxy
- Docker: deployment

---

## 7. Output Requirements

System must include:
- FastAPI application
- SQLAlchemy models
- Alembic migrations
- HTMX UI
- Alpine.js interactions
- Docker + Docker Compose setup
- Nginx configuration
- Uvicorn server configuration
- Raspberry Pi deployment ready setup

# Backlog

1.	Add a floating + button in lower right corner (mobile)
2.	Add back to top floating link in lower right corner
3.	update recipe delete to delete all child tables OR add delete date (AFTER all testing)
4. - none
5.	add navbar search field
6.	Search history should only be saved if it returns greater than one result
7.	- How are the cooked count and ingredient counts   remove Recipe.cooked_count and Recipe.ingredient_count from DB
8.	Add recipe cooked count to recipe list card thumbnails, bottom left
9.	The confirmation for Delete Resipe should be a modal, not a seperate page.
10.	After deleting a recipe the scroll position is lost when going back to the recipe list
11.	Add ability to sort inredients dynamiclly within a recipe in the UI

# Backlog (UI follow-up completed locally 2026-10-13)
make 1.	Add a floating + button in lower right corner also available on desktop
There appear to be duplicate search fields in the navbar header
navbar search fields should have the same 'Recent searches' functionality as the recipe list page (is shold be the same list)
11.	Add ability to sort inredients dynamiclly within a recipe in the UI - make this a click and drag operation (more modern)
2.	Add back to top floating link in lower right corner - make this animated so the move to top is not so abrupt


### Backlog for Future Implementations
- Web scraping 
  - Build AI scraper to get instructions etc
  - Add a scraper to navigate to the source URL and get the Print PDF
  - add check in scraper library to look for headers (that probably have <3 spaces in the text?) (possibly OBE)
  - add scraper library to helpers
  - add scraper library to recipe edit page
- Use Claude and apify to scrape recipe Audrey
  - Scraper: maybe use Crawl4ai


- Update the cookbook PDF generator (C:\projects\MyRecipeSite\cookbook.py) to resolve PDF formatting issues 
- Add LLMs to synonym and spelling error lookup
- Use Plotly? Add a Recently Visited section to the home page
- What are your thoughts on moving image storage to NAS (192.168.1.14)?
    - store images in a structured directory
- DONE: Smart collection "Never cooked" shows recipes with no cooking-history records.

- For public usage
  - Login + authentication
  - Flask-Limiter

### Backlog from Codex agent
- DONE add the same sort options on the home page recipe list that exist on prod
- DONE: Create/edit ingredient input method uses one-click radio options.
- DONE: Recipe pagination offers 12, 24, 48, or 96 recipes per page.
- DONE: Back/Cancel restores the recipe list filters and scroll position.
- DONE: Favorite button on recipe detail adds/removes the Favorites collection. Favorite stars appear at the upper left of recipe cards, meal-plan cards, and create/edit image previews.
- DONE: /frontend-design (https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md)
set up the design system using the frontend-design skill. Think premium recipe platform: one restrained accent color, high-contrast text, tight typography. Define the design tokens, the thumbnail card (thumbnail, title, meta line, favorite badge), and the grid rhythm for the recipe list. I like the clean look of bon appetit (e.g. https://www.bonappetit.com/recipe/gochujang-yogurt-chicken   Gochujang Yogurt Chicken Recipe _ Bon Appétit.pdf). For now only show me 3 example styled recipe pages at /design so I can judge it before we build real pages.
 
- DONE: Add PDF export template for Recipe pages. Also allow for printing all recipes for a printable recipe book. (after /frontend design)

 What changes have you made to the database that will require a deployment stratefy to prod?
 how will the alias data get to prod?