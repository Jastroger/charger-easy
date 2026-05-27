# Legacy compatibility wrappers

This folder is intentionally kept only for old manual commands. New code and
new helper scripts should live in `charger_easy/tools/`.

Automated tests live in `tests/`.

The compatibility entry point still works:

```bash
sudo python3 test/set-cc.py
```

Preferred direct command:

```bash
sudo python3 -m charger_easy.tools.set_current 6
```

Use `--eeprom` only when you intentionally want to write the MCP4161 EEPROM register `0x20`.
The default writes the volatile RAM register `0x00`.

Automated tests do not need Raspberry Pi hardware:

```bash
python -m unittest discover -s tests
python -m pytest
```

The local fake web dashboard for development runs through the package tool:

```bash
python -m charger_easy.tools.fake_web
```
