# My Project

A brand new project.

# Onboarding / Reminder

## Clone this repo
- How to clone a GitHub repo: https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository
- How to clone a git repo: https://git-scm.com/book/en/v2/Git-Basics-Getting-a-Git-Repository

## Install Python
Get it from https://www.python.org/downloads/  

## Get ready to run an example
- Open a command/terminal and navigate to the cloned repo location.
- Create a [venv](https://docs.python.org/3/library/venv.html#creating-virtual-environments) ***[OPTIONAL]***
    - `python -m venv .venv`
    - Windows: `"C:\Program Files\Python311\python.exe" -m venv .venv311` *if you want to target a specific python version.*
- Enable your [venv](https://docs.python.org/3/library/venv.html#creating-virtual-environments) ***[OPTIONAL]***
    - Windows/PowerShell: `.venv\Scripts\Activate.ps1`
    - Windows/PowerShell: `.venv311\Scripts\Activate.ps1` *if you want to target your specific python version.*  
    - When you're not sure to have your venv enabled, you can check if your default python executable is located in your virtual environment.  
    Check where is located your default python executable `python -c "import sys; print(sys.executable)"`  
    If your [venv](https://docs.python.org/3/library/venv.html#creating-virtual-environments) is enable, it should return something like: `.venv\Scripts\python.exe`
- Upgrade `pip`  
`python -m pip install --upgrade pip`
- Install the dependencies with [pip](https://pip.pypa.io/en/stable/cli/pip_install/):  
`pip install -r requirements.txt`
- Run it!  
`python.exe -m examples.main main`

# Development Environment
## Tests
### Run tests
- All the tests:  
`python -m unittest discover -v -s "tests" -p "*_test.py" -t "."`
- A test file:  
`python -m unittest -v 'tests.unit.fibonacci_test'`
- A test class:  
`python -m unittest -v 'tests.unit.fibonacci_test.Fibo_Test'`
- A single test:  
`python -m unittest -v 'tests.unit.fibonacci_test.Fibo_Test.test_callWithValidInput_0'`

### Code Coverage
[`coverage`](https://pypi.org/project/coverage/) is part the installed packages, you just need to:
- Run the unit tests with `coverage`:
    - All the unit tests: `coverage run -m unittest discover -s "tests" -p "*_test.py" -t "."`
    - A specific unit test: `coverage run -m unittest -v 'tests.unit.fibonacci_test.Fibo_Test.test_callWithValidInput_0'`
- Generate the coverage results:  
    - `coverage report`  
    Text version of the coverage results
    - `coverage report --format=total`  
    Total coverage result (no details)
    - `coverage lcov`  
    Will generate an `lcov.info` file that will be processed by [`Coverage Gutters` extension](https://marketplace.visualstudio.com/items?itemName=ryanluker.vscode-coverage-gutters) in `Visual Studio Code`. `.vscode/settings.json` is configured accordingly.
    - `coverage html`  
    Will generate an HTML version of the coverage results. You may access those from `<repo>/htmlcov/index.html`.

### Linter
[`flake8`](https://pypi.org/project/flake8/) is part the installed packages, you just need to:
- run [`flake8`](https://pypi.org/project/flake8/) on the repo:  
`python -m flake8 .`
- Check if any error has been reported.

You may also access [`flake8`](https://pypi.org/project/flake8/) from [VSCode](https://code.visualstudio.com/) if you installed [flake 8 extension](https://marketplace.visualstudio.com/items?itemName=ms-python.flake8)

## IDE
- Install VSCode:  
https://code.visualstudio.com/
    - Install Python extension: (***[REQUIRED]*** to run/debug)  
    https://marketplace.visualstudio.com/items?itemName=ms-python.python
    - Install Python formatter: (***[REQUIRED]*** to edit code)  
    https://marketplace.visualstudio.com/items?itemName=ms-python.autopep8
    - Install Python Linter: (***[REQUIRED]*** to edit code)  
    https://marketplace.visualstudio.com/items?itemName=ms-python.flake8
    - Install command variable: (Used for some configurations in `launch.json`)***[OPTIONAL]***  
    https://marketplace.visualstudio.com/items?itemName=rioj7.command-variable
    - Install TODO extension to see pending work: ***[OPTIONAL]***  
    https://marketplace.visualstudio.com/items?itemName=Gruntfuggly.todo-tree
    - Display test coverage results on files: ***[OPTIONAL]***  
    https://marketplace.visualstudio.com/items?itemName=ryanluker.vscode-coverage-gutters

## Keep dependencies up-to-date
- Keep track of your dependencies:  
    - `pip list` List all the installed dependencies...meaning all the dependencies you've explicitly installed and their implicit dependencies)  
    - `pip freeze` Same as `pip list`, but respecting the [requirements](https://pip.pypa.io/en/stable/reference/requirements-file-format/) file format
- Update dependencies  
Edit the `requirements.txt` file. Only add the explicit dependency you need, not their internal/recursive dependencies. To not lose your sanity, you may want to install [pip-chill](https://pypi.org/project/pip-chill/) and/or [pipdeptree](https://pypi.org/project/pipdeptree/).
- Check if your dependencies have all they need: `pip check`
- Want to start with a clean slate:
    - `pip freeze > clean_dependencies.txt`
    - `pip uninstall -r clean_dependencies.txt -y`
