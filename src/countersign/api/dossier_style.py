"""The stylesheet, inline. Sober on purpose: this is read once, at speed.

The palette follows the business-case document so the two read as one product.
Fonts are system stacks because the page must render with no network at all.
"""

DOSSIER_CSS = """
:root{--paper:#EDEFF2;--surface:#F7F8FA;--sunk:#E3E7EB;--ink:#141C26;--ink-2:#4E5A69;
--ink-3:#77828F;--rule:#C7CFD8;--rule-soft:#DCE2E8;--seal:#93242A;--seal-soft:#F6E6E6;
--verify:#14655F;--verify-soft:#DCEAE8;--amber:#8A5A08;--amber-soft:#F5E9D4;
--sans:ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
--serif:Georgia,"Iowan Old Style","Times New Roman",serif;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root{--paper:#0E1319;--surface:#161C24;--sunk:#1C242D;
--ink:#E2E8EE;--ink-2:#A2AEBB;--ink-3:#7A8794;--rule:#2C3742;--rule-soft:#222B34;
--seal:#E88D91;--seal-soft:#331A1C;--verify:#6FBDB4;--verify-soft:#13272A;
--amber:#D5A45C;--amber-soft:#2B2214}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:inherit}
.sheet{max-width:920px;margin:0 auto;background:var(--surface);
border-left:1px solid var(--rule-soft);border-right:1px solid var(--rule-soft);
min-height:100vh;padding:0 0 64px}
.masthead{padding:36px 44px 24px;border-bottom:1px solid var(--rule)}
.brand{font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--ink-3);
font-weight:600}
.masthead h1{font-family:var(--serif);font-size:27px;line-height:1.2;margin:10px 0 16px;
font-weight:600}
.facts{display:flex;flex-wrap:wrap;gap:10px 28px;margin:0;font-size:13px}
.facts div{min-width:0}
.facts dt{color:var(--ink-3);font-size:11px;letter-spacing:.1em;text-transform:uppercase}
.facts dd{margin:2px 0 0;font-family:var(--mono);font-size:12.5px;color:var(--ink-2)}
.verdict{padding:28px 44px 30px;border-bottom:1px solid var(--rule);background:var(--sunk)}
.verdict--high{background:var(--seal-soft);border-bottom-color:var(--seal)}
.verdict--review{background:var(--amber-soft);border-bottom-color:var(--amber)}
.verdict--clear{background:var(--verify-soft);border-bottom-color:var(--verify)}
.verdict--none{background:var(--sunk)}
.verdict--none .headline{font-size:24px;color:var(--ink-2)}
.level{display:inline-block;font-size:11.5px;font-weight:700;letter-spacing:.18em;
text-transform:uppercase;padding:5px 11px;border-radius:2px;color:var(--surface);
background:var(--ink-2)}
.verdict--high .level{background:var(--seal)}
.verdict--review .level{background:var(--amber)}
.verdict--clear .level{background:var(--verify)}
.headline{font-family:var(--serif);font-size:30px;line-height:1.24;margin:16px 0 0;
font-weight:600;max-width:26em}
.action{margin:18px 0 0;max-width:44em;padding-left:14px;border-left:3px solid var(--rule)}
.action b{display:block;font-size:11px;letter-spacing:.14em;text-transform:uppercase;
color:var(--ink-3);margin-bottom:3px}
.arith{margin:16px 0 0;font-family:var(--mono);font-size:12.5px;color:var(--ink-2)}
section{padding:30px 44px 6px;border-bottom:1px solid var(--rule-soft)}
section:last-of-type{border-bottom:0}
h2.sub{margin:26px 0 12px;padding-top:18px;border-top:1px solid var(--rule-soft)}
h2{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-3);
margin:0 0 4px;font-weight:700;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.lede{margin:0 0 18px;color:var(--ink-2);font-size:13.5px;max-width:52em}
.tally{font-family:var(--mono);letter-spacing:0;text-transform:none;font-weight:500;
padding:2px 8px;border-radius:2px;background:var(--sunk);color:var(--ink-2);font-size:11.5px}
.tally--seal{background:var(--seal);color:var(--surface)}
.claims{list-style:none;margin:0;padding:0}
.claim{border-top:1px solid var(--rule-soft);padding:16px 0}
.claim:first-child{border-top:0}
.claim-head{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
.kind{font-family:var(--mono);font-size:12px;color:var(--seal);font-weight:600}
.kind--plain{color:var(--ink-3)}
.weight{font-family:var(--mono);font-size:11.5px;color:var(--ink-3)}
.statement{margin:7px 0 12px;font-size:16px;max-width:46em}
.sources{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.source{background:var(--sunk);border-left:3px solid var(--rule);padding:9px 12px;
border-radius:0 2px 2px 0;font-size:12.5px;overflow-wrap:anywhere}
.provider{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;font-weight:700;
color:var(--ink-3);margin-right:8px}
.locator{font-family:var(--mono);font-size:12.5px;color:var(--verify)}
a.locator:hover{text-decoration-thickness:2px}
.box{font-family:var(--mono);font-size:11.5px;color:var(--ink-3);margin-left:8px}
.snippet{margin:6px 0 0;color:var(--ink-2);font-style:italic;max-width:52em}
.unsourced{background:var(--seal);color:#fff;padding:10px 12px;border-radius:2px;
font-weight:700;font-size:13px}
.trace{list-style:none;margin:0;padding:0;counter-reset:step}
.step{display:grid;grid-template-columns:26px 1fr auto;gap:12px;align-items:baseline;
padding:11px 12px;border-left:3px solid var(--rule-soft);background:var(--surface)}
.step+.step{border-top:1px solid var(--rule-soft)}
.step .n{font-family:var(--mono);font-size:12px;color:var(--ink-3)}
.step .who{font-weight:600;font-size:14px}
.step .what{font-family:var(--mono);font-size:12px;color:var(--ink-2);margin-top:2px;
overflow-wrap:anywhere}
.step .stage{font-family:var(--mono);font-size:11px;color:var(--ink-3);
letter-spacing:.08em;text-transform:uppercase}
.pill{font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;
padding:3px 8px;border-radius:2px;background:var(--sunk);color:var(--ink-2);white-space:nowrap}
.step--ok .pill{background:var(--verify-soft);color:var(--verify)}
.step--denied{background:var(--seal-soft);border-left:5px solid var(--seal);
padding:18px 14px;margin:10px 0;border-top:0}
.step--denied+.step{border-top:0}
.step--denied .pill{background:var(--seal);color:#fff}
.step--denied .who{color:var(--seal)}
.step--denied .n{color:var(--seal)}
.reason{grid-column:2/4;margin:8px 0 0;color:var(--ink);font-size:14.5px;max-width:46em}
.reason b{color:var(--seal)}
.gate{grid-column:2/4;margin:6px 0 0;font-family:var(--mono);font-size:11.5px;
color:var(--ink-2)}
.strip{list-style:none;margin:0 0 16px;padding:0;display:flex;flex-wrap:wrap;gap:6px}
.chip{font-family:var(--mono);font-size:11.5px;padding:4px 9px;background:var(--sunk);
border-left:3px solid var(--rule);color:var(--ink-2);border-radius:0 2px 2px 0}
.chip--completed{border-left-color:var(--verify);color:var(--verify)}
.chip--degraded{border-left-color:var(--amber);color:var(--amber)}
.chip--skipped{border-left-color:var(--amber)}
.chip--failed{border-left-color:var(--seal);color:var(--seal)}
.errors{list-style:none;margin:0;padding:0;display:grid;gap:6px}
.error{border-left:3px solid var(--seal);background:var(--seal-soft);padding:9px 12px;
font-family:var(--mono);font-size:12.5px;overflow-wrap:anywhere}
.skipped{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.skip{border-left:3px solid var(--amber);background:var(--amber-soft);padding:10px 12px;
font-size:13px}
.skip .what{font-weight:600}
.skip .env{font-family:var(--mono);font-size:12px;color:var(--ink-2);margin-top:3px}
.empty{color:var(--ink-3);font-size:13.5px;margin:0 0 16px}
footer{padding:26px 44px;color:var(--ink-3);font-size:12px}
@media (max-width:640px){.masthead,.verdict,section,footer{padding-left:20px;
padding-right:20px}.headline{font-size:24px}.masthead h1{font-size:22px}}
"""

__all__ = ["DOSSIER_CSS"]
