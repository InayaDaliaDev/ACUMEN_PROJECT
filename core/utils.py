import json, re

def extract_text(content):
    if isinstance(content, str): return content
    if isinstance(content, list):
        return ''.join(b if isinstance(b,str) else b.get('text','') for b in content if isinstance(b,(str,dict)))
    return str(content or '')

def is_plausible_gemini_key(key):
    key=(key or '').strip(); return len(key)>=20 and ' ' not in key

def extract_json_block(text):
    text=extract_text(text).strip()
    if not text: return None
    text=re.sub(r'^```(?:json)?\s*','',text); text=re.sub(r'\s*```$','',text)
    try: return json.loads(text)
    except Exception: pass
    for a,b in [('{','}'),('[',']')]:
        i,j=text.find(a),text.rfind(b)
        if i>=0 and j>i:
            try: return json.loads(text[i:j+1])
            except Exception: pass
    return None
