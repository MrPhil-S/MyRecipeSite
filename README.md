# MyRecipeSite

**The Problem**
Create a central mobile-friendly site that provides the ability to store recipes from various sources and can be relied upon as a recipe book that can be used for years to come. It should not be reliant on a cloud service that is subject to change. search by ingredient. 
When there are ingredients in the house that need to be used before going bad, there is no quick way to find which saved recipes use the ingredient.  
Store recipe ingredients and instructions text locally to protect against the source website from switching to monitized system, requiring a subscriptions or goes down and is no longer available.
Be able to export recipes to PDF for easy printing.

**The Plan**
FastAPI v2 is the current app. Local development uses native Windows Python 3.12;
the existing Pi installations use Uvicorn/systemd with a separate MariaDB server.

From `C:\projects\MyRecipeSite`, start the local app with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\recipe_app_v2\start_native.ps1
```

Open `http://127.0.0.1:8001/`. The launcher uses the private root `config.ini`
dev section, `MyRecipes_DEV`, and `recipe_app_v2\uploads`. The native virtual
environment is `C:\Users\<WindowsUser>\MyRecipeSite_Local\.venv`.
Replace `<WindowsUser>` with the Windows profile folder name; the PowerShell
commands in the app guide use `$env:USERPROFILE` automatically.
See [native setup and validation](recipe_app_v2/README.md) and the
[deployment guide](deployment/README.md). Pi changes require
a separate assignment; follow root `AGENTS.md` for the deferred cooked-date feature.

****

****

****

****
