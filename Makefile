# useful actions

SYSTEM_PYTHON := /usr/bin/python3

PROJECT := asyncio_cmdline
DEPENDENCIES := blessed
TESTS := tests
VENV := venv

ACTIVATE := . $(VENV)/bin/activate
FIND := /usr/bin/find
RM := /bin/rm
SETUP := ./setup.py
VIRTUALENV := /usr/bin/virtualenv

VENV_PIP := $(VENV)/bin/pip
VENV_PYTHON := $(VENV)/bin/python

PYFILES := $(wildcard $(PROJECT)/*.py $(PROJECT)/*/*.py $(PROJECT)/*/*/*.py)

.PHONY: clean
clean:
	$(SYSTEM_PYTHON) $(SETUP) clean --all
	$(RM) -rf -- $(PROJECT).egg-info
	$(FIND) $(PROJECT) $(TESTS) -type f -name '*.pyc' -delete
	$(FIND) $(PROJECT) $(TESTS) -depth -type d -name '__pycache__' -delete

.PHONY: cleanvenv
cleanvenv:
	$(RM) -rf -- $(VENV)

$(VENV):
	$(VIRTUALENV) --python=$(SYSTEM_PYTHON) $(VENV)
	$(VENV_PIP) install --upgrade coverage ipython pytest $(DEPENDENCIES)

.PHONY: install
install: $(VENV)
	$(VENV_PIP) install --upgrade --force-reinstall .

.PHONY: test
test: $(VENV)
	$(VENV_PYTHON) $(SETUP) test

.coverage: $(VENV) $(PYFILES)
	$(VENV_PYTHON) -m coverage run --source $(PROJECT) $(SETUP) test

.PHONY: coverage
coverage: $(VENV) .coverage
	$(VENV_PYTHON) -m coverage report -m

.PHONY: sdist
sdist: $(VENV)
	$(VENV_PYTHON) $(SETUP) sdist

.PHONY: bdist
bdist: $(VENV)
	$(VENV_PYTHON) $(SETUP) bdist

.PHONY: wheel
wheel: $(VENV)
	$(VENV_PYTHON) $(SETUP) bdist_wheel

.PHONY: dists
dists: sdist bdist wheel
