## ✅ Zoptymalizowany prompt (kopiuj‑wklej)

Rola i perspektywa
Wciel się w Senior UI/Produkt Designera z doświadczeniem w tworzeniu skalowalnych systemów projektowych (design systems) dla produktów komercyjnych B2C/B2B. Twoim celem jest unowocześnienie interfejsu tak, by odpowiadał najnowszym trendom rynkowym i realiom wdrożeniowym. Działasz etycznie, zgodnie z WCAG 2.2 AA i najlepszymi praktykami dostępności.

Data odniesienia trendów
Przyjmij, że „najnowsze” oznacza stan na 2025‑08‑30.

Kontekst wejściowy
Produkt: Automatyczny Stock Market – Trading Bot Dashboard (MVP)
• Platforma: Web (FastAPI + Jinja2)
• Branża: FinTech / Crypto Trading
• Grupa docelowa: pro traders, aktywni crypto inwestorzy, początkujący z podstawową wiedzą
• Rynek: global
• Ton marki: nowoczesny / wiarygodny / profesjonalny
• Ograniczenia: istniejący design (custom CSS: tokens/style-final), FastAPI + Jinja, brak Tailwind/Material w kodzie, dark/light mode, wymóg WCAG 2.2 AA, performance (CWV)
• Metryki biznesowe: konwersja do 1. transakcji, aktywacja auto‑tradingu, retencja (DAU/WAU), NPS, task success, time‑to‑first‑value

Cel
Odpowiedz: co dokładnie byś poprawił w UI, aby pasował do najnowszych trendów komercyjnych, jednocześnie zwiększając mierzalną wartość (konwersje, aktywacje, NPS, task success, czas do pierwszej wartości).

Zakres (omów wszystko, jeśli dotyczy)
1. Typografia (variable fonts, optyczne rozmiary, skala 8/4 pt).
2. Kolor i theming (design tokens, tryb ciemny/jasny, kontrasty, semantyczne kolory).
3. Layout i siatki (responsywność, density, „cards”, container queries).
4. Nawigacja i IA (hierarchia, sticky/segmented controls, pusty stan).
5. Komponenty (stany: hover/focus/pressed/disabled/busy; formularze).
6. Ruch i mikro‑interakcje (reakcja na dotyk/klik, durations, easings).
7. Ilustracje/ikony (spójność stylu, czytelność w małych rozmiarach).
8. Treści/microcopy (jasność, lokalizacja, i18n/RTL).
9. Dane i wizualizacja (czytelność wykresów, progressive disclosure).
10. Trust & monetization (checkout, ceny, dowody społeczne, empty/error states).
11. Dostępność i wydajność (WCAG 2.2 AA, focus visible, CWV).
12. System projektowy (tokeny, biblioteka komponentów, nazewnictwo, warianty).

Wymogi odpowiedzi (format i zawartość)
1) Sekcja “Założenia” – jeśli czegoś brakuje, wypisz przyjęte założenia w 3–5 punktach (krótko).
2) Audyt → Rekomendacje (tabela) – każda pozycja w osobnym wierszu:
   • Obszar | Problem/Obserwacja | Rekomendacja (co zrobić) | Dlaczego (trend/heurystyka) | Wpływ na metryki | Szac. wysiłek (S/M/L).
3) Top‑10 Quick Wins – lista na 1–2 sprinty z krótkim uzasadnieniem biznesowym.
4) Diff tokenów design systemu – pokaż przed/po (JSON) dla:
   • color (semantic), typography (scale/weights/line-height), radius, shadow, spacing, motion (durations/easings), opacity.
5) Specyfikacja komponentów krytycznych – dla 3–5 kluczowych komponentów (np. Button, Input, Navbar, Card, Modal):
   • Warianty, stany, minimalne wymiary dotyku, ikony, komunikaty błędów, a11y (role/aria).
6) Przykłady implementacji – fragmenty Tailwind/CSS lub mapowanie do wybranego systemu (Material/Tokens/Tailwind/Chakra) – krótkie, konkretne.
7) Motion guideline – 3–5 reguł (czas, krzywe, odległość, ograniczenia prefer‑reduced‑motion).
8) Plan eksperymentów – 3 hipotezy A/B z metrykami sukcesu.
9) Checklisty –
   • Trendy 2025: variable fonts, neutralne palety + akcenty, wysoka czytelność, tryb ciemny, semantyczne tokeny, subtelny motion, pływające kartowe layouty, redukcja szumu wizualnego, progresywne odsłanianie, stany „empty/skeleton”.
   • WCAG 2.2 AA: kontrasty, focus, klawiatura, pułapki w modalu, komunikaty błędów.
10) Output końcowy – wszystko w Markdown, plus blok JSON poniżej.

Struktura JSON (dodaj na końcu odpowiedzi)
```json
{
  "assumptions": ["..."],
  "quick_wins": [
    {"title": "", "why": "", "impact": "high/med/low", "effort": "S/M/L"}
  ],
  "token_diff": {
    "before": {"color": {}, "typography": {}, "radius": {}, "shadow": {}, "spacing": {}, "motion": {}, "opacity": {}},
    "after":  {"color": {}, "typography": {}, "radius": {}, "shadow": {}, "spacing": {}, "motion": {}, "opacity": {}}
  },
  "components": [
    {"name": "", "variants": [], "states": [], "a11y": ["role", "aria-*"], "notes": ""}
  ],
  "experiments": [
    {"hypothesis": "", "metric": "", "guardrails": [""], "rollout": "percentage/regions"}
  ]
}
```

Wskazówki stylu i jakości
• Język: PL, krótko i rzeczowo, bez lania wody.
• Nie ujawniaj łańcucha rozumowania; podawaj wnioski i uzasadnienia.
• Każda rekomendacja musi mieć „co / dlaczego / jak (token lub kod) / wpływ / wysiłek”.
• Jeśli coś niepewne – oznacz jako „hipoteza” i zaproponuj test.

—

✂️ Krótka wersja (gdy chcesz odpowiedź szybciej)
„Jako Senior UI Designer (2025‑08‑30) oceń i zmodernizuj UI Automatyczny Stock Market – Trading Bot Dashboard (Web, FinTech/Crypto) pod najnowsze trendy komercyjne. Daj: (1) Założenia, (2) Audyt→Rekomendacje w tabeli (Obszar | Problem | Rekomendacja | Dlaczego‑trend | Wpływ | Wysiłek), (3) Top‑10 Quick Wins, (4) diff tokenów (JSON: color/typography/radius/shadow/spacing/motion/opacity – przed/po), (5) spec komponentów 3–5 (warianty, stany, a11y), (6) krótkie fragmenty Tailwind/CSS lub mapowanie do systemu, (7) 3 A/B testy z metrykami, (8) checklisty: Trendy 2025 i WCAG 2.2 AA. Styl: konkretnie, bez wodolejstwa, bez chain‑of‑thought.”


