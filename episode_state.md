# Diamond no Ace S3 (act II) — Translation State

Running context for the EN→MN subtitle project. Update every ~50 translated lines.

## Progress LALAR

| Episode | Raw | Output | Status |
|---|---|---|---|
| 01 | — | `mn-finished/DACE03_01.ass` | Done (pre-existing) |
| 02 | — | `mn-finished/DACE03_02.ass` | Done (pre-existing) |
| 03 | `raw/DACES03_03.ass` | `mn-finished/DACE03_03.ass` | **Done** — L35–L104 were already translated in the raw file and were kept verbatim; L105–L373 translated this session |
| 04 | `raw/DACES03_04.ass` | — | Not started (fully English) |

Note: raw files are named `DACES03_NN.ass`, outputs drop the S → `DACE03_NN.ass`.

## Story so far

- **Ep 01–02:** Seidou reaches Koushien for the first time in 7 years. Furuya has become
  the ace (jersey #1) and throws 154 km/h against Nihon Shouno. Seidou advances through
  the early rounds. Komadai Fujimaki's Hongou Masamune is introduced as the standout
  2nd-year ace who dominated Shoubi 10–0.
- **Ep 03 ("Бэйсболийн Гоц Авьяастан"):** Quarterfinal, Seidou vs Komadai Fujimaki.
  Hongou (2nd year, catcher Enjou Renji) shuts Seidou down with 150 km/h fastballs and a
  brutal splitter; Kuramochi, Toujou and Kominato all go down in the first. Furuya gives up
  2 runs in the bottom of the 1st, then settles. Coach Nitta's monologue frames Hongou as
  "blessed by the baseball gods"; Nitta deliberately plays the villain to make him grow.
  Flashback: Hongou and Furuya both come from Hokkaido, never faced each other in junior
  high; Enjou saw Furuya closing at the Jingu tournament. Miyuki finally breaks up the
  no-hitter in the 5th. Score still **Komadai 2 – Seidou 0** after 7. Ep 04 continues the
  same game.

## Established names (Cyrillic — do not change)

Савамүра (Эйжүн) · Фүрүяа (Саторү) · Миюүки (Казүяа) · Күрамочи · Коминато / Харүчи ·
Канэмарү · Тожо · Ширасү · Маэзоно · Накада · Хигаса · Сэки · Катаока (дасгалжуулагч) ·
Очиай · Хонго Масамүнэ · Энжо (Рэнжи) · Нитта (дасгалжуулагч) · Ниши · Тодороки · Мишима ·
Минэ · Овада · Юй · Сэто · Окүмүра · Эзаки · Сүги · Ота · Ширакава
Teams/places: Сэйдо · Комадай Фүжимаки · Кошиэн · Нихон Шоно · Яакүши · Инаширо · Жингү ·
Хоккайдо · Аоба · Томакомай

## Terminology

| EN | MN |
|---|---|
| pitch / pitching | шидэлт |
| pitcher / catcher / batter | шидэгч / баригч / цохигч |
| hit | цохилт |
| ace | эйс |
| run, score | оноо |
| out / double play | гаралт / давхар гаралт |
| home run | хөүм-ран |
| fastball | хурдан шидэлт |
| splitter / slider | сплиттер / слайдер |
| bunt / sacrifice bunt | бант / золиослолын бант |
| runner | гүйгч |
| base (1st/2nd/3rd) | талбар (1-р / 2-р / гуравдугаар) |
| shortstop / center field | Шорт / Төв Талбар |
| control | удирдлага |
| captain / senpai / coach | ахмад / -сэнпай / дасгалжуулагч |

**Umpire calls:** Strike! → `Страйк!` · Strike two! → `Хоёр дахь страйк!` ·
Strike three, you're out! → `Гурван страйк! Гарлаа!` · Ball! → `Гадаа!` (established ep 01) ·
Foul! → `Фоул!` · Out! → `Гарлаа!` · Play ball! → `Эхэл!`

**Innings** use the compact convention from ep 01–02: top of the 1st = `1-1-р хагас`,
bottom of the 1st = `1-2-р хагас`, bottom of the 7th = `7-2-р хагас`.

**Sawamura's ドンマイ ("don't mind")** → `Зүгээр ээ!` (stuttered: `Зү, зү, зүгээр ээ!`).

## Episode titles

- Ep 01 — "Мөрөөдлийн Цаана."
- Ep 02 — "Хурдан Зогсмоор Байна."
- Ep 03 — "Бэйсболийн Гоц Авьяастан." (fixed by ep 02's next-episode card)
- Ep 04 — "Бүх Зүйл Эхэлсэн Өдөр." (coined in ep 03's preview — reuse in ep 04)

Next-episode card phrasing: `"Бэйсбол Талбайн Эйс"-ийн {\i0}Дараагийн Ангид{\i1}:`
Closing line: `Улсын аваргын төлөө!`

## File conventions

- UTF-8 **with BOM**, **CRLF** line endings, trailing newline.
- Translate **only** the Text field (after the 9th comma). Never touch Layer/Start/End/
  Style/Name/Margins/Effect — timings must stay byte-identical.
- Preserve override tags exactly: `{\an8}` (announcer/top-positioned), `{\i1}`/`{\i0}`
  (internal monologue), `{\fad(...)}`, and `\N` manual line breaks.
- Leave `chapter` lines (`{OP}`, `{ED}`, `{Preview}`) untranslated.
- Do **not** reorder lines — the user runs `an8collector/an8collector.py` afterwards to move
  `{\an8}` lines to the bottom of `[Events]` (it aborts if the byte size changes).
