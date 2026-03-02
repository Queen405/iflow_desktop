# AGENTS.md - iFlow Desktop

Guidelines for AI agents working on the iFlow Desktop codebase.

## Project Overview

iFlow Desktop is a PySide6-based GUI application for the iFlow CLI tool. It provides a native desktop interface for managing iFlow Bot services, configuration, and chat interactions.

## Build/Lint/Test Commands

### Install Dependencies
```bash
# Using uv (recommended)
uv pip install -e ".[dev]"

# Or using pip
pip install -e ".[dev]"
```

### Run the Application
```bash
# Method 1: Entry point command
iflow-desktop

# Method 2: Python module
python -m iflow_desktop

# Method 3: Direct execution
python src/iflow_desktop/app.py
```

### Testing
```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_file.py

# Run a single test function
pytest tests/test_file.py::test_function_name

# Run with verbose output
pytest -v
```

### Type Checking (if configured)
```bash
# Install mypy if not present
pip install mypy

# Run type checking
mypy src/iflow_desktop
```

## Code Style Guidelines

### General Principles
- Python 3.10+ required
- Use `from __future__ import annotations` in all files
- Follow PEP 8 naming conventions
- Write docstrings for modules, classes, and public methods

### Imports
- Group imports in this order:
  1. `from __future__ import annotations` (first line)
  2. Standard library imports
  3. Third-party imports (PySide6, pydantic, etc.)
  4. Local application imports
- Use absolute imports: `from iflow_desktop.core.cli_bridge import ...`
- Lazy imports acceptable for heavy dependencies to improve startup time

### Naming Conventions
- **Classes**: PascalCase (e.g., `MainWindow`, `ChatPage`, `StatusMonitor`)
- **Functions/Methods**: snake_case (e.g., `_init_ui()`, `_on_click()`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `NAV_ITEMS`)
- **Private members**: Prefix with underscore (e.g., `_monitor`, `_pages`)
- **Qt Object Names**: Use objectName for styling (e.g., `setObjectName("Sidebar")`)

### Type Hints
- Use modern Python typing syntax:
  - `str | None` instead of `Optional[str]`
  - `dict[str, type]` instead of `Dict[str, Type]`
  - `list[str]` instead of `List[str]`
- Type all function parameters and return values
- Use `typing.Optional` sparingly (prefer `| None`)

### Error Handling
- Use try/except for expected failures (file operations, subprocess calls)
- Silent failures acceptable for UI updates (use `pass` in except)
- Log or handle errors appropriately in core logic
- Always validate Qt object validity before access in async contexts:
  ```python
  try:
      obj.objectName()
      return True
  except RuntimeError:
      return False
  ```

### Qt/PySide6 Patterns
- **Signals**: Define at class level with type annotations
  ```python
  page_changed = Signal(str)
  ```
- **Background Work**: Use QThread for expensive operations, never block UI
- **Lazy Loading**: Delay page creation until first navigation
- **Resource Management**: Clean up threads in `closeEvent()`

### File Organization
```
src/iflow_desktop/
├── app.py              # Application entry point
├── main_window.py      # Main window with navigation
├── core/               # Core business logic
│   └── cli_bridge.py   # CLI command wrappers
├── widgets/            # UI components
│   ├── sidebar.py      # Navigation sidebar
│   ├── chat.py         # Chat interface
│   └── ...             # Other pages
└── resources/          # Static resources
    └── style.py        # Qt stylesheets
```

### Documentation Style
- Module docstrings: Brief description in Chinese (project standard)
- Class docstrings: One-line description
- Method docstrings: Describe purpose for public methods
- Comments: Use Chinese for UI-related explanations, English for technical logic

### Configuration
- User config stored in `~/.iflow/settings.json`
- Use `IFlowSettings` class for config access
- Workspace data in `~/.iflow-bot/`

### UI Guidelines
- Use Catppuccin Mocha color scheme (defined in `resources/style.py`)
- Set object names for all styled widgets
- Support high DPI: Call `QApplication.setHighDpiScaleFactorRoundingPolicy()` before app creation
- Minimum window size: 1100x700, default: 1360x820

## Testing

- Tests live in `tests/` directory (create if needed)
- Use pytest fixtures for Qt application setup
- Mock subprocess calls and file system operations
- Test background thread logic separately from UI

## Dependencies

### Runtime
- PySide6 >= 6.6.0 (GUI framework)
- pydantic >= 2.0.0 (data validation)
- pydantic-settings >= 2.0.0 (configuration)

### Development
- pytest >= 9.0.2 (testing)
- mypy (type checking - add if needed)
- ruff (linting - add if needed)

## Packaging

Build executable with PyInstaller:
```bash
pip install pyinstaller
pyinstaller --name "iFlow Desktop" --windowed --onefile src/iflow_desktop/app.py
```

## Pre-commit Checklist

- [ ] All imports sorted and grouped correctly
- [ ] Type hints present on public functions
- [ ] Docstrings added for new modules/classes
- [ ] Qt object names set for styled widgets
- [ ] Background threads properly cleaned up in closeEvent
- [ ] No blocking operations in main thread
