set -e
T=$(sudo cat /opt/plane-chat-app/plane_token)
P=$(sudo docker ps --format '{{.Names}}' | grep -E 'plane-app-proxy' | head -1)
IP=$(sudo docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "$P" | awk '{print $1}')
export T IP
python3 - <<'PY'
import os,json,urllib.request,urllib.error
T=os.environ["T"]; IP=os.environ["IP"]; WS="workspaces/caryaar"
def api(method,p,body=None):
    r=urllib.request.Request(f"http://{IP}/api/v1/{p}",data=json.dumps(body).encode() if body is not None else None,method=method,
        headers={"X-Api-Key":T,"Host":"pitstop.mycaryaar.com","Content-Type":"application/json"})
    try:
        raw=urllib.request.urlopen(r).read(); return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e: return {"_error":e.code,"_body":e.read().decode()[:250]}
D="@caryaar.com"
# project identifier -> list of (email, is_lead); lead only set on the three new projects
MAP={
 "WR":[("hiren.machhar",True),("joel.dsouza",False)],
 "PARTNER":[("zoeb.amiruddin",True),("joel.dsouza",False)],
 "HR":[("reema.lewis",True),("humanresource",False),("maxson.lewis",False)],
 "OPS":[("janhavi.nanaware",False),("anagha.khedekar",False),("hiren.machhar",False),("joel.dsouza",False)],
 "MKT":[("kaushik.chavan",False),("priya.vaishya",False),("maxson.lewis",False)],
 "BRAND":[("kaushik.chavan",False),("priya.vaishya",False),("maxson.lewis",False)],
 "FINANCE":[("shubham.rane",False),("maxson.lewis",False)],
 "CORP":[("maxson.lewis",False),("joel.dsouza",False)],
}
wm=api("GET",f"{WS}/members/"); wm=wm if isinstance(wm,list) else wm.get("results",[])
by_email={m["email"].lower():m for m in wm}
print("WORKSPACE MEMBERS:",sorted(by_email))
print("BHAVANA still member:", "bhavana.srivastava@caryaar.com" in by_email)
projs={p["identifier"]:p for p in api("GET",f"{WS}/projects/?per_page=100")["results"]}
print("HR network:",projs["HR"]["network"],"(0 = private, 2 = public)")
pending=[]
for ident,people in MAP.items():
    p=projs[ident]; base=f"{WS}/projects/{p['id']}"
    pm=api("GET",base+"/members/"); pm=pm if isinstance(pm,list) else pm.get("results",[])
    have={m.get("email","").lower() for m in pm}
    for user,lead in people:
        email=user+D; w=by_email.get(email)
        if not w: pending.append(f"{ident}:{user}"); continue
        if email not in have:
            role=20 if (w.get("role")==20 and lead) else 15
            r=api("POST",base+"/members/",{"member":w["id"],"role":role})
            print(f"ADD {email} -> {ident} role {role}:", "ok" if "_error" not in r else r)
        if lead and p.get("project_lead")!=w["id"]:
            r=api("PATCH",base+"/",{"project_lead":w["id"]})
            print(f"LEAD {ident} -> {email}:", "ok" if "_error" not in r and r.get("project_lead")==w["id"] else r)
print("WAITING FOR ACCEPT:",pending)
PY
