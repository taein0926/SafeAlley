import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("./searchPanel.css", import.meta.url), "utf8");
const picker = readFileSync(new URL("./components/ExamplePicker.tsx", import.meta.url), "utf8");

test("search errors retain their position and get the same bottom padding as the weather top gap", () => {
  assert.match(app, /<div className="search-weather">[^\n]*<\/div>\s*\{requestState === "error" && <p className="route-error" role="alert">[^\n]*\s*<\/section>/);
  const chrome = readFileSync(new URL("./mapChrome.css", import.meta.url), "utf8");
  assert.match(chrome, /#route-search-panel:has\(\.route-error\) \{ padding-bottom: 10px; \}/);
  assert.match(chrome, /#route-search-panel \.route-error \{ margin-top: 0; \}/);
});

test("examples animate input without searching; the search button retains the existing route handler", () => {
  assert.match(app, /밤 10시에 도화119안전센터에서 두리하나어린이집 및 육아종합지원센터까지 가려고 해\. 가로등이 많고 계단 없는 길로 안내해줘\./);
  assert.match(app, /밤 8시에 서화초에서 실버타운까지 가로등, CCTV 많은 길로 안내해줘\. 계단도 피해서 안내해\./);
  assert.match(app, /낮 2시에 인천비즈니스고등학교에서 와이지타워까지 CCTV가 많고 건널목을 적게 건너는 길로 안내해줘\./);
  const examplesArray = app.match(/const SEARCH_EXAMPLES = \[([\s\S]*?)\] as const;/)?.[1];
  assert.equal(examplesArray?.match(/"[^"\n]+"/g)?.length, 4);
  const examples = examplesArray?.match(/"[^"\n]+"/g)?.map(value => JSON.parse(value));
  assert.equal(examples?.[1], "밤 8시에 서화초에서 실버타운까지 가로등, CCTV 많은 길로 안내해줘. 계단도 피해서 안내해.");
  assert.match(app, /await runAiSearch\(query\)/);
  assert.match(app, /onSelect=\{typeExample\}/);
  assert.match(picker, /setOpen\(false\); onSelect\(example\)/);
  const example = app.slice(app.indexOf("function typeExample"), app.indexOf("function editQuery"));
  assert.match(example, /livePreview.clear\(\)/);
  assert.match(example, /exampleTyper.current\?\.start\(text\)/);
  assert.doesNotMatch(example, /runAiSearch|queryRouteWithProgress|beginSearch/);
  const sharedSearch = app.slice(app.indexOf("async function runAiSearch"), app.indexOf("const selectRoute ="));
  assert.match(sharedSearch, /requestState === "loading" \|\| !text.trim\(\)/);
  assert.match(sharedSearch, /setMode\("ai"\)/);
  assert.match(sharedSearch, /setQuery\(text\)/);
  assert.match(sharedSearch, /queryRouteWithProgress\(text.trim\(\), userId/);
  assert.equal(app.match(/await queryRouteWithProgress\(/g)?.length, 1);
  assert.match(picker, /aria-label="예시 경로 검색"/);
  assert.match(app, /\{displayedCandidates.length === 0 && requestState !== "loading" && !candidateSelection && <div className="search-empty">/);
});

test("example selector opens the same four element-only labels above the button in two columns", () => {
  assert.ok(app.indexOf('<ExamplePicker') < app.indexOf('className="search-button"'));
  assert.equal(app.match(/<ExamplePicker/g)?.length, 1);
  assert.match(picker, /open && <div/);
  assert.match(picker, /className="search-example-label">\{LABELS\[index\]\}/);
  assert.match(picker, /"가로등 · 계단", "가로등 · CCTV · 계단", "가로등 · 건널목", "CCTV · 건널목"/);
  assert.doesNotMatch(picker, /많음|회피/);
  assert.doesNotMatch(picker, /<span>\{example\}<\/span>/);
  assert.match(picker, /disabled=\{disabled\}/);
  assert.match(picker, /event.key !== "Escape"/);
  assert.match(picker, /document.addEventListener\("pointerdown", outside\)/);
  assert.match(css, /\.search-examples \{ display: grid; grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); gap: 6px;.*bottom: calc\(100% \+ 8px\);.*margin: 0;/);
  assert.match(css, /\.search-examples button \{[^}]*min-height: 32px;[^}]*background: #f5f8fc;/);
});

test("compact route badges align small icons and labels without visible status text", () => {
  const cards = readFileSync(new URL("./routeCards.css", import.meta.url), "utf8");
  assert.match(cards, /padding: 12px 14px;/);
  assert.match(cards, /repeat\(4, minmax\(0, 1fr\)\)/);
  assert.match(cards, /\.recommendation-icons svg \{ width: 16px; height: 16px;/);
  assert.doesNotMatch(cards, /recommendation-badge-status/);
  const badges = readFileSync(new URL("./components/RecommendationIcons.tsx", import.meta.url), "utf8");
  assert.match(badges, /aria-label=\{`\$\{CONDITION_LABELS\[factor\]\}: \$\{status\}`\}/);
  assert.doesNotMatch(badges, /<small|recommendation-badge-status/);
});

test("taller sentence input reserves the smaller microphone footprint", () => {
  assert.match(css, /--speech-button-size: 28\.8px;/);
  assert.match(css, /--speech-button-inset: 12px;/);
  assert.match(css, /--search-input-height: 124\.8px;/);
  assert.match(css, /--direct-input-height: 83px;/);
  assert.match(css, /\.place-inputs \{ height: var\(--direct-input-height\); grid-template-rows: minmax\(0, 1fr\) 1px minmax\(0, 1fr\);/);
  assert.match(css, /\.ai-query textarea \{\s+height: var\(--search-input-height\);\s+min-height: var\(--search-input-height\);\s+resize: none;\s+padding: 14px calc\(var\(--speech-button-size\) \+ var\(--speech-button-inset\) \+ 4px\) 14px 16px;/);
  assert.match(css, /\.speech-actions button \{ width: var\(--speech-button-size\); height: var\(--speech-button-size\);/);
  assert.match(css, /\.speech-actions button svg \{ width: 16px; height: 16px;/);
});

test("streetlight density legend uses the white panel palette even on the night map", () => {
  const styles = readFileSync(new URL("./styles.css", import.meta.url), "utf8");
  const legend = styles.match(/\.density-legend \{([^}]+)\}/)?.[1] ?? "";
  assert.match(legend, /color: #202735; background: #fff;/);
  assert.match(legend, /border: 1px solid #e3e7ed;/);
  assert.match(app, /nightMode && facilityVisibility.streetlights/);
});

test("shorter direct inputs offset the collapsed criteria row and preserve centered pins", () => {
  assert.match(css, /\.place-inputs input \{\s+min-height: 0;\s+height: 100%;/);
  assert.match(css, /padding: 6px 14px;/);
  assert.match(css, /\.location-input button img \{ width: 22\.4px; height: 28px; \}/);
  assert.match(css, /\.criteria-toggle \{\s+align-items: center;\s+min-height: var\(--criteria-toggle-height\);/);
});

test("pin dividers occupy only the centered eighty percent of each input row", () => {
  const button = css.match(/#route-search-panel \.location-input button \{([^}]+)\}/)?.[1] ?? "";
  assert.match(button, /position: relative;/);
  assert.match(button, /border: 0;/);
  assert.doesNotMatch(button, /border-left/);
  const divider = css.match(/#route-search-panel \.location-input button::before \{([^}]+)\}/)?.[1] ?? "";
  assert.match(divider, /top: 10%;/);
  assert.match(divider, /bottom: 10%;/);
  assert.match(divider, /width: 1px;/);
  assert.match(divider, /pointer-events: none;/);
});

test("criteria contents use ninety percent width without shrinking the outer box", () => {
  assert.match(css, /\.route-criteria > :is\(\.departure-time-control, \.preference-slider\) \{\s+width: 90%;\s+justify-self: center;/);
});

test("criteria add top breathing room and tighten only the space below each slider", () => {
  const criteria = css.match(/#route-search-panel \.route-criteria \{([^}]+)\}/)?.[1] ?? "";
  assert.match(criteria, /padding: 16px 12px 12px;/);
  assert.match(css, /\.preference-slider \{ gap: 2px; \}/);
  assert.match(css, /\.preference-slider input\[type="range"\] \{ margin: 4px 0 0; \}/);
});

test("expanded criteria match the existing visible label gap without changing collapsed search height", () => {
  assert.match(css, /#route-search-panel:has\(\.place-inputs\) \.search-mode-toolbar \{ margin-top: var\(--direct-search-gap\); \}/);
  assert.match(css, /\.route-form \{ width: var\(--search-content-width\); margin: 10px auto 0; gap: var\(--direct-search-gap\); \}/);
  const criteria = css.match(/#route-search-panel \.route-criteria \{([^}]+)\}/)?.[1] ?? "";
  assert.match(criteria, /margin-top: 0;/);
  assert.match(criteria, /margin-bottom: 5\.4px;/);
  const toolbar = app.slice(app.indexOf('<div className="search-mode-toolbar">'), app.indexOf('{requestState === "error" &&'));
  assert.doesNotMatch(toolbar, /criteriaOpen/);
});

test("both search modes restore full width and original compact spacing", () => {
  assert.match(css, /--search-content-width: 100%;/);
  assert.match(css, /--criteria-toggle-height: 30px;/);
  assert.match(css, /--ai-toolbar-gap: 16px;/);
  assert.match(css, /--direct-search-gap: calc\(\(var\(--search-input-height\) \+ var\(--ai-toolbar-gap\) - var\(--direct-input-height\) - var\(--criteria-toggle-height\)\) \/ 2\);/);
  assert.match(css, /\.search-mode-toolbar \{[^}]*width: var\(--search-content-width\); margin: var\(--ai-toolbar-gap\) auto 0;/);
});

test("departure input fills the slider-width wrapper while preserving button size, padding and border", () => {
  const row = css.match(/#route-search-panel \.route-criteria > \.departure-time-control \{([^}]+)\}/)?.[1] ?? "";
  assert.match(row, /display: flex;/);
  assert.match(row, /width: 90%;/);
  assert.match(row, /gap: 8px;/);
  assert.match(row, /justify-content: flex-start;/);
  assert.match(row, /justify-self: center;/);
  const input = css.match(/#route-search-panel \.departure-time-control input \{([^}]+)\}/)?.[1] ?? "";
  assert.match(input, /flex: 1;\s+width: 100%;/);
  assert.match(input, /height: 37\.44px;\s+padding: 6px 10px;/);
  assert.match(input, /border-color: var\(--search-line\);/);
  assert.doesNotMatch(css, /::-webkit-calendar-picker-indicator/);
});

test("preference labels describe priority and crosswalk avoidance without changing weight mapping", () => {
  assert.match(app, /label="경로 우선순위" value=\{safetyWeight\} onChange=\{setSafetyWeight\} levelLabels=\{\["거리", "균형", "안전"\]\}/);
  assert.match(app, /label="계단 회피" value=\{stairsWeight\} onChange=\{setStairsWeight\}/);
  assert.match(app, /label="횡단보도 회피" value=\{crossingWeight\} onChange=\{setCrossingWeight\}/);
  assert.doesNotMatch(app, /label="안전 관련 시설"|label="건널목 회피"/);
});

test("Korean brand keeps reload and the agreed slogan without a comma", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  assert.match(html, /<title>안전골목길<\/title>/);
  assert.match(app, /aria-label="안전골목길 새로고침" onClick=\{\(\) => window.location.reload\(\)\}/);
  assert.match(app, /<strong>안전골목길<\/strong>/);
  assert.match(app, /className="brand-slogan">골목에 안전을 더하다<\/p>/);
  const header = app.slice(app.indexOf('<header className="sidebar-header"'), app.indexOf('<section id="route-search-panel"'));
  assert.doesNotMatch(header, /<WeatherHud/);
  assert.match(app, /className="search-weather"><WeatherHud \{\.\.\.weather\} requested=\{weatherRequested\} \/>/);
  assert.match(css, /\.brand-row \{ align-items: flex-start;/);
});

test("compact actions and symmetric header preserve equal input and example edge gaps", () => {
  assert.match(css, /--search-action-height: 32px;/);
  assert.match(css, /height: var\(--search-action-height\);/);
  assert.match(css, /min-height: var\(--search-action-height\);/);
  assert.match(css, /--search-edge-gap: 18px;/);
  assert.match(css, /padding: 8px 20px var\(--search-edge-gap\);/);
  assert.match(css, /\.route-form \{[^}]*margin: 10px auto 0;/);
  assert.match(css, /\.sidebar-header \{ --brand-logo-line-height: 30px; padding: 14px 20px; \}/);
  assert.match(css, /\.brand-chip strong \{ line-height: var\(--brand-logo-line-height\); \}/);
  const chrome = readFileSync(new URL("./mapChrome.css", import.meta.url), "utf8");
  assert.match(chrome, /\.weather-hud-heading \{[^}]*display: block;[^}]*width: 100%;[^}]*text-align: center;/);
  assert.match(chrome, /\.weather-hud-values > span \{ display: inline-flex; align-items: center; min-height: 0; line-height: 18px; \}/);
});

test("slogan and weather rows have no extra vertical spacing", () => {
  assert.match(css, /\.brand-identity \{[^}]*gap: 0;/);
  const chrome = readFileSync(new URL("./mapChrome.css", import.meta.url), "utf8");
  const styles = readFileSync(new URL("./styles.css", import.meta.url), "utf8");
  assert.match(chrome, /\.weather-hud-values \{[^}]*margin-top: 0;/);
  assert.match(chrome, /\.weather-hud-unavailable \{[^}]*margin-top: 0;/);
  assert.match(styles, /\.weather-hud-values \{[^}]*margin-top: 0;/);
});

test("weather is separated by spacing without an upper divider", () => {
  const chrome = readFileSync(new URL("./mapChrome.css", import.meta.url), "utf8");
  assert.doesNotMatch(chrome, /\.search-weather::before/);
  assert.match(chrome, /\.search-weather \{[^}]*margin: 0 auto;[^}]*padding: 10px 12px;[^}]*border: 0;/);
});

test("sentence input starts empty with a placeholder and uses existing search handlers", () => {
  assert.match(app, /useState<SearchMode>\("ai"\)/);
  assert.match(app, /\[query, setQuery\] = useState\(""\)/);
  assert.match(app, /placeholder="어디로, 어떤 길로 가고 싶나요\?"/);
  assert.match(app, /onSubmit=\{searchWithAi\}/);
  assert.match(app, /onSubmit=\{searchDirect\}/);
  assert.equal(app.match(/"검색 중\.\.\." : "길찾기"/g)?.length, 1);
  assert.match(app, /type="submit" form="route-search-form"/);
  assert.doesNotMatch(app, /role="tablist"|>AI 검색<|>직접 검색</);
});

test("one accessible icon switch preserves input and cancels pending building selection", () => {
  const toolbar = app.slice(app.indexOf('<div className="search-mode-toolbar">'), app.indexOf('{requestState === "error" &&'));
  assert.match(toolbar, /aria-label=\{mode === "ai" \? "직접 설정" : "문장 입력"\}/);
  assert.match(toolbar, /title=\{mode === "ai" \? "직접 설정" : "문장 입력"\}/);
  assert.match(toolbar, /disabled=\{requestState === "loading"\}/);
  assert.match(toolbar, /\+\+buildingRequestSerial.current/);
  assert.match(toolbar, /setBuildingSelectionMode\(null\)/);
  assert.match(toolbar, /setMode\(mode === "ai" \? "direct" : "ai"\)/);
  assert.doesNotMatch(toolbar, /setQuery|setOriginLocation|setDestinationLocation/);
  assert.match(css, /\.search-mode-toolbar \{ display: flex; align-items: center;/);
  assert.ok(toolbar.indexOf('className="search-mode-switch"') < toolbar.indexOf('className="search-button"'));
  assert.match(toolbar, /M3 5h4m4 0h10M3 12h10m4 0h4M3 19h4m4 0h10/);
});
