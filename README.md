# kit-generator

Генератор комплектов формы (kit) для GameplayFootball из данных Transfermarkt:
цвета берутся из профиля клуба на TM, при их отсутствии — извлекаются из логотипа.

Поддерживает **клубы** и **национальные сборные**.

Два этапа работы:

1. **Пакетная генерация** — `generate_kits.py`: для каждого клуба/сборной собирает палитру и
   генерирует **6 комплектов** (main/white/black/reserve + gk1/gk2), рендерит PNG 1024×1024
   по `template_kit.png` из игры.
2. **Ручной редактор** — `editor/server.py` (web): по очереди показывает клуб с логотипом
   и цветами, позволяет схематично назначить цвета частям формы и узор футболки для
   каждого комплекта; «далее» принимает и сгенерированные скриптом сочетания.

Набор китов и правило шортов/гетр: полевые комплекты — футболка в заданный цвет, шорты/гетры
равны цвету футболки либо нейтралу (вторичный цвет клуба, если он белый/чёрный); белый и
чёрный комплекты цельные; гк1/гк2 — два ярких цельных вратарских цвета из стандартного пула.
Выбор форм на матч (конвенция + ручной оверрайд) — `kits/spec.py::pick_match_kits`, см. `NOTES.md`.

**Связанные клубы** (основной + академия + вторая команда) объединяются в группы по имени
(`kits/linked.py`): дети наследуют палитру и киты корня, правка в редакторе любого члена
распространяется на всю группу.

## Зависимости

- Python 3.10+
- Pillow, numpy (`pip install -r requirements.txt`)

## Быстрый старт

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt

# Клубы
.venv/Scripts/python generate_kits.py \
    --clubs ../transfermarkt_scrapper/data/full/clubs.json \
    --logos ../transfermarkt_scrapper/data/images/logos \
    --template data/GameplayFootball/data/databases/default/template_kit.png \
    --out out

# Национальные сборные
.venv/Scripts/python generate_kits.py \
    --teams ../transfermarkt_scrapper/data/full/national_teams.json \
    --logos ../transfermarkt_scrapper/data/images/emblems \
    --template data/GameplayFootball/data/databases/default/template_kit.png \
    --out out/national
```

## Входы

| Что | Откуда |
|---|---|
| клубы с цветами и лигами | `../transfermarkt_scrapper/data/full/clubs.json` (TM-скрейпер) |
| национальные сборные с цветами | `../transfermarkt_scrapper/data/full/national_teams.json` (TM-скрейпер) |
| логотипы клубов `<id>.png` | `../transfermarkt_scrapper/data/images/logos/` |
| эмблемы сборных `<id>.png` | `../transfermarkt_scrapper/data/images/emblems/` |
| шаблон кита `template_kit.png` | репозиторий GameplayFootball |

## Выходы

```
out/
  specs.json          # спекы всех клубов (палитра + 6 комплектов)
  <club_id>/
    main.png  white.png  black.png  reserve.png  gk1.png  gk2.png
```

## Схема спеки

```json
{
  "id": "131",
  "name": "FC Bayern München",
  "palette": ["#DC052D", "#FFFFFF", "#1C3F94", "#32CD32", "#FF8C00"],
  "main":    {"shirt": 0, "shorts": 1, "socks": 1, "pattern": "plain", "pattern_color": null},
  "white":   {"shirt": 1, "shorts": 1, "socks": 1, "pattern": "plain", "pattern_color": null},
  "black":   {"shirt": 3, "shorts": 3, "socks": 3, "pattern": "plain", "pattern_color": null},
  "reserve": {"shirt": 2, "shorts": 1, "socks": 1, "pattern": "plain", "pattern_color": null},
  "gk1":     {"shirt": 3, "shorts": 3, "socks": 3, "pattern": "plain", "pattern_color": null},
  "gk2":     {"shirt": 4, "shorts": 4, "socks": 4, "pattern": "plain", "pattern_color": null}
}
```

Цвета в спеках — индексы в `palette` клуба (профильные TM-цвета, затем производные из
логотипа, затем нейтрали; гк-цвета добавляются при необходимости). Узоры:
`plain`, `stripes`, `hoops`, `sash`, `halves`.

## Выбор китов на матч

```python
from kits.spec import pick_match_kits
pick_match_kits(spec_a, spec_b)                     # конвенция (home в main, гость переодевается)
pick_match_kits(spec_a, spec_b, manual={"b": "reserve"})  # ручной оверрайд
# -> {"a_out", "b_out", "a_gk", "b_gk"} — имена комплектов
```

## Редактор

```bash
.venv/Scripts/python editor/server.py --specs out/specs.json --logos ../transfermarkt_scrapper/data/images/logos
# http://localhost:9001
```

Изменения в редакторе сохраняются в `out/specs.json` (клубы помечаются `edited` и не
перезаписываются при повторной генерации без `--specs`); PNG перегенерируются по спекам.

## Экспорт в игру

```bash
# Клубы
.venv/Scripts/python export_game.py \
    --specs out/all/specs.json --kits out/all \
    --out ../GameplayFootball/data/databases/default/images_teams

# Национальные сборные (экспортируются в images_teams/national/)
.venv/Scripts/python export_game.py \
    --specs out/national/specs.json --kits out/national \
    --out ../GameplayFootball/data/databases/default/images_teams
```

Кладутся `images_teams/<league_id>/<club_id>_kit_main/white/black/reserve/gk1/gk2.png`.
Для сборных: `images_teams/national/<team_id>_kit_*.png`. Финальное именование `_kit_01..06`
и укладку в игровой каталог данных делает конвертер `tm-gf-import` (`builders/files.py`, `KIT_MAP`).
Игра пока умеет только `_kit_01/_02` + общий `goalie_kit.png`; подключение набора китов и
матчевого выбора — правка `team.cpp`/меню, см. `NOTES.md`.