.PHONY: check

# Round-trip the synthetic fixtures and the collision cases.
check:
	python3 tests/check.py
