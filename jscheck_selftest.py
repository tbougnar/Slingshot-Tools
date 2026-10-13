"""Do the no-node checks cry wolf on JavaScript that is actually valid?"""
import make_app

GOOD = [
    'const K="x";localStorage.setItem(K,"1");',
    'const re=/\\d+/g;',
    'const t=`a ${b} c`;',
    'const n=`line1\nline2`;',
    'const q="it\'s fine";',
    'const d="a\\"b";',
    'if(a){b()}else{c()}',
    'const s="`";',
    'const arrow=x=>`${x}`;',
    'try{a()}catch{b()}',
]

print("valid javascript, must report nothing:")
bad = 0
for src in GOOD:
    got = make_app._unbalanced_delimiters(src)
    if got:
        bad += 1
        print(f"  FALSE POSITIVE  {src[:46]:48s} -> {got}")
    else:
        print(f"  ok              {src[:46]}")

BAD = [
    ('const x=getElementById("outputUnit`).value;', "wrong closing char"),
    ('const a="unclosed;', "never closed"),
    ('const b=`unclosed template;', "never closed template"),
    ('if(a{ b() }', "unclosed paren"),
]

print("\ninvalid javascript, must report something:")
missed = 0
for src, why in BAD:
    got = make_app._unbalanced_delimiters(src)
    if not got:
        missed += 1
        print(f"  MISSED          {src[:46]:48s} ({why})")
    else:
        print(f"  caught          {src[:46]:48s} -> {got}")

print(f"\nfalse positives: {bad}   missed: {missed}")
raise SystemExit(1 if (bad or missed) else 0)