---
name: legacy-codebase-analysis
description: Analyze legacy/unknown codebases remotely (SSH, Windows/Linux) — discover structure, identify entry points, trace architecture, and produce comprehensive technical documentation in phased stages.
category: software-development
metadata:
  hermes:
    tags: [analysis, documentation, reverse-engineering, game-dev, codebase-audit, ssh-exploration]
---

# Legacy Codebase Analysis

Analyze an unfamiliar or legacy codebase to produce comprehensive technical documentation. Covers remote exploration via SSH, architecture identification, entry point tracing, and phased documentation output.

## Triggers

- "Analyze this project/codebase/repository"
- "I need technical documentation for this code"
- "What does this project do, how is it structured?"
- "Help me understand this legacy code"
- "Document the architecture of this project"
- User points to a project directory and asks for analysis

## Workflow

### Phase 1: Discovery (Top-Level Structure)

1. **Explore root directory** — list top-level folders and files to identify project type:
   ```powershell
   # Windows via SSH
   Get-ChildItem '<project_root>' | Select-Object Name, PSIsContainer
   
   # Linux/Unix
   find . -maxdepth 2 -not -path './.git/*' | head -100
   ```

2. **Identify project type indicators:**
   - `Assets/` + `ProjectSettings/` + `*.unity` → Unity game project
   - `go.mod` or `GOPATH`-style `src/` → Go project
   - `package.json` → Node.js
   - `pom.xml` / `build.gradle` → Java
   - `protocol/` + `*.proto` → Protobuf-based communication
   - `client/` + `server/` → C/S architecture

3. **Map directory structure** at depth 2-3 for each major section:
   ```powershell
   Get-ChildItem '<root>\client' -Recurse -Depth 2 | Select-Object FullName, PSIsContainer
   ```

### Phase 2: Entry Points

Find and read key entry files:

| Project Type | Entry Files |
|---|---|
| Unity C# | `ProjectSettings/ProjectVersion.txt`, `EditorBuildSettings.asset`, `GameCtrl.cs` or similar bootstrap MonoBehaviour |
| Go | `main.go`, `server.go`, `init()` functions |
| Node.js | `package.json` (main/start), `index.js`, `app.js` |
| Java | `Application.java`, `Main.java`, `pom.xml` dependencies |
| Python | `__main__.py`, `setup.py`, `requirements.txt` |

**Entry point patterns to look for:**
- Unity: `Awake()`, `Start()`, `DontDestroyOnLoad`, scene bootstrapper
- Go: `func main()`, `init()` package-level initialization, `node.Setup()` / `service.Start()`
- General: singleton factories, dependency injection containers, module registration

### Phase 3: Architecture Extraction

Read core architecture files to understand:

1. **Framework layer** — base classes, interfaces, patterns:
   - `IGameModule`, `Singleton<T>`, `GameState` → module/state-machine architecture
   - `IService`, `RunLoop()` → event-loop service architecture
   - `BaseController`, `ViewModel` → MVC/MVVM

2. **Communication layer** — how components talk:
   - Protocol files (`*.proto`) → message definitions
   - `NetProxy`, `NetTCP` → network abstraction
   - `EventMgr`, `event.go` → event/pub-sub system
   - `rpc/` directory → inter-service RPC

3. **Business modules** — enumerate functional modules:
   - Game modules: `LoginModule`, `BagModule`, `ShopModule`, etc.
   - Server services: `gateway`, `game`, `login`, `rank`, `relation`

4. **Data layer**:
   - Config tables: Excel → JSON → runtime loading
   - Database: MySQL, MongoDB, Redis
   - ORM or raw SQL

### Phase 4: Documentation

Produce structured output:

1. **Executive summary** — project type, language, architecture, scale
2. **Directory tree** — annotated structure with purpose of each section
3. **Tech stack** — frameworks, libraries, tools, versions
4. **Architecture diagrams** — component relationships, data flow
5. **Entry point trace** — step-by-step startup sequence
6. **Module inventory** — catalog of business modules with brief descriptions
7. **Protocol specification** — message types, RPC interfaces
8. **Deployment notes** — startup scripts, config, database setup

### Phase 5: Phased Deep-Dive Plan

For large codebases, propose a phased plan for deeper analysis:
- Each phase focuses on one subsystem
- Each phase produces incremental documentation
- Prioritize based on user's stated goals

## Remote Exploration Techniques

### Windows via SSH

```bash
# List directories
ssh host "powershell -NoProfile -Command \"Get-ChildItem 'C:\path\to\project' | Select-Object Name, PSIsContainer\""

# Recursive listing with depth
ssh host "powershell -NoProfile -Command \"Get-ChildItem 'C:\path' -Recurse -Depth 2 | Select-Object FullName, PSIsContainer\""

# List files only
ssh host "powershell -NoProfile -Command \"Get-ChildItem 'C:\path' -File | Select-Object Name\""

# Read file content
ssh host "powershell -NoProfile -Command \"Get-Content 'C:\path\to\file.cs'\""

# Count files by extension
ssh host "powershell -NoProfile -Command \"Get-ChildItem 'C:\path' -Recurse -File | Group-Object Extension | Select-Object Name, Count\""
```

### Linux via SSH

```bash
# Tree-like listing
ssh host "find /path -maxdepth 2 -not -path '*/.git/*' | sort"

# File counts by type
ssh host "find /path -type f -name '*.cs' | wc -l"
ssh host "find /path -type f | sed 's/.*\.//' | sort | uniq -c | sort -rn"

# Read file
ssh host "cat /path/to/file"
ssh host "head -50 /path/to/file"
```

## Pitfalls

- **Path spaces**: Windows paths with spaces need quotes in PowerShell: `'C:\path with spaces\file'`
- **Encoding issues**: PowerShell output may show garbled characters for Chinese/non-ASCII filenames. Use `-Encoding UTF8` or accept that directory names with non-ASCII chars may be unreadable via SSH.
- **Context window management**: For large codebases, read files selectively. Read entry points and architecture files first, not every source file.
- **Don't enumerate everything**: When listing UI pages or modules, capture the pattern and count rather than listing every single item.
- **Go GOPATH vs modules**: Old Go projects use `src/` with GOPATH layout (no `go.mod`). Newer projects use `go.mod` with module paths. Check which before analyzing imports.
- **Unity project settings**: `ProjectVersion.txt` tells you the Unity version. `EditorBuildSettings.asset` lists build scenes. `ProjectSettings.asset` has player settings.

## Game Project Specific Patterns

Common patterns in game projects (Unity client + Go server):

- **Client**: Unity C#, Addressables for resources, DOTween for animation, Protobuf for network, module system for game features
- **Server**: Go with custom framework, Redis for hot data, MySQL/MongoDB for persistence, Protobuf RPC for inter-service communication
- **Protocol**: Shared `.proto` files, codegen to C# and Go
- **Config**: Excel → JSON → runtime loading on both sides
- **Services**: Gateway (connection), Game (logic), Login (auth), Center (account), DB (persistence), Rank (leaderboards), Relation (social)

## Output Style

- Use plain text for terminal rendering (avoid heavy Markdown tables)
- Include concrete file paths and line counts
- Provide architecture as ASCII diagrams where possible
- Be specific about versions (Unity version, Go version, library versions)
- When uncertain, state what needs further investigation rather than guessing
