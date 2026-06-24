
import json
import csv
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict, deque
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

APP_TITLE = "Harris Matrix Editor 6.0 PRO"
BOX_W = 86
BOX_H = 34
LAYER_Y = 82
COL_X = 118

TYPE_STYLE = {
    "SURFACE": ("#7ECF73", "oval"),
    "TOP_SURFACE": ("#7ECF73", "oval"),
    "GEOLOGY": ("#7ECF73", "oval"),
    "UNEXCAVATED": ("#CFCFCF", "rect"),
    "DEPOSIT": ("#8DBBE8", "rect"),
    "STRUCTURAL": ("#9FC4E8", "rect"),
    "CUT": ("#E98B8B", "rect"),
    "FILL": ("#F3B562", "rect"),
    "UNKNOWN": ("#EEEEEE", "rect"),
}
EDGE_ABOVE = "ABOVE"
EDGE_LATER = "LATER"
EDGE_CONTEMP = "CONTEMPORARY"

GRAPHML_NS = "http://graphml.graphdrawing.org/xmlns/graphml"
NS = {"g": GRAPHML_NS}

def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default

def safe_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default

def xml_escape(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

class HarrisMatrixEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1500x930")
        self.nodes = {}
        self.edges = []
        self.groups = []
        self.project = {"Name":"", "Description":"", "ExcavationSite":""}
        self.selected_node = None
        self.selected_group = None
        self.selected_edge_index = None
        self.drag = (0,0)
        self.drag_mode = None
        self.zoom = 1.0
        self.filename = None
        self.show_temporal = tk.BooleanVar(value=True)
        self.show_invalid = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Ready")
        self._build_ui()
        self.new_project()

    # ---------- UI ----------
    def _build_ui(self):
        toolbar = tk.Frame(self)
        toolbar.pack(fill=tk.X)
        buttons = [
            ("New", self.new_project), ("Open HMCX", self.open_hmcx), ("Open JSON", self.open_json),
            ("Save JSON", self.save_json), ("Export HMCX", self.export_hmcx), ("Export PDF", self.export_pdf), ("Export SVG", self.export_svg),
            ("+ Surface", lambda:self.add_node_dialog("SURFACE")), ("+ Deposit", lambda:self.add_node_dialog("DEPOSIT")),
            ("Above", lambda:self.add_relation_dialog(EDGE_ABOVE)), ("Later", lambda:self.add_relation_dialog(EDGE_LATER)), ("Contemp.", lambda:self.add_relation_dialog(EDGE_CONTEMP)),
            ("Phase box", self.add_group_dialog), ("Collapse", self.toggle_group),
            ("Auto layout", self.auto_layout), ("Clean lines", self.remove_transitive_edges), ("Validate", self.validate_show),
            ("Search", self.search_dialog), ("Fit", self.fit_view), ("Zoom +", lambda:self.set_zoom(self.zoom*1.18)), ("Zoom -", lambda:self.set_zoom(self.zoom/1.18)),
        ]
        for label, cmd in buttons:
            tk.Button(toolbar, text=label, command=cmd).pack(side=tk.LEFT, padx=1, pady=2)
        tk.Checkbutton(toolbar, text="Temporal", variable=self.show_temporal, command=self.draw).pack(side=tk.LEFT, padx=4)
        tk.Checkbutton(toolbar, text="Invalid marks", variable=self.show_invalid, command=self.draw).pack(side=tk.LEFT)

        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)
        left = tk.Frame(paned)
        paned.add(left, stretch="always")
        self.canvas = tk.Canvas(left, bg="white", scrollregion=(0,0,4200,3200))
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll = tk.Scrollbar(left, orient=tk.VERTICAL, command=self.canvas.yview)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll = tk.Scrollbar(left, orient=tk.HORIZONTAL, command=self.canvas.xview)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        right = tk.Frame(paned, width=350)
        paned.add(right)
        tk.Label(right, text="Inspector", font=("Arial", 13, "bold")).pack(anchor="w", padx=6, pady=(6,0))
        self.props = tk.Text(right, height=13, width=42, font=("Consolas", 9))
        self.props.pack(fill=tk.X, padx=6)
        tk.Button(right, text="Apply inspector changes", command=self.apply_properties).pack(fill=tk.X, padx=6, pady=3)
        tk.Label(right, text="Relations", font=("Arial", 12, "bold")).pack(anchor="w", padx=6, pady=(8,0))
        self.rel_list = tk.Listbox(right, height=13)
        self.rel_list.pack(fill=tk.BOTH, expand=True, padx=6)
        self.rel_list.bind("<<ListboxSelect>>", self.relation_select)
        tk.Button(right, text="Delete selected relation", command=self.delete_selected_relation).pack(fill=tk.X, padx=6, pady=3)
        tk.Label(right, text="Messages / Search", font=("Arial", 12, "bold")).pack(anchor="w", padx=6, pady=(8,0))
        self.msg_list = tk.Listbox(right, height=10)
        self.msg_list.pack(fill=tk.BOTH, expand=True, padx=6)
        self.msg_list.bind("<Double-Button-1>", self.message_double_click)
        tk.Button(right, text="Clear messages", command=lambda:self.msg_list.delete(0,tk.END)).pack(fill=tk.X, padx=6, pady=3)

        tk.Label(self, textvariable=self.status, anchor="w", relief=tk.SUNKEN).pack(fill=tk.X)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Double-Button-1>", self.on_double)
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<ButtonPress-2>", self.pan_start)
        self.canvas.bind("<B2-Motion>", self.pan_move)
        self.canvas.bind("<ButtonPress-3>", self.pan_start)
        self.canvas.bind("<B3-Motion>", self.pan_move)

    # ---------- Coordinate helpers ----------
    def sx(self, x): return x*self.zoom
    def sy(self, y): return y*self.zoom
    def ux(self, x): return x/self.zoom
    def uy(self, y): return y/self.zoom

    # ---------- Data ----------
    def new_project(self):
        self.project = {"Name":"", "Description":"", "ExcavationSite":""}
        self.nodes = {
            "T": {"id":"T", "label":"Top", "name":"Top surface", "description":"", "type":"TOP_SURFACE", "layer":0, "x":520, "y":40, "valid":True},
            "U": {"id":"U", "label":"Unexcavated", "name":"Unexcavated", "description":"", "type":"UNEXCAVATED", "layer":1, "x":500, "y":180, "w":130, "valid":True},
            "G": {"id":"G", "label":"Geology", "name":"Interface to Geology", "description":"", "type":"GEOLOGY", "layer":2, "x":490, "y":320, "w":150, "valid":True},
        }
        self.edges = [
            {"id":"e1", "source":"T", "target":"U", "type":EDGE_ABOVE, "valid":True},
            {"id":"e2", "source":"U", "target":"G", "type":EDGE_ABOVE, "valid":True},
        ]
        self.groups=[]
        self.selected_node=None; self.selected_group=None; self.selected_edge_index=None
        self.filename=None
        self.draw()
        self.status.set("New minimal Harris Matrix created")

    def import_loaded_data(self, nodes, edges, groups=None, project=None):
        self.nodes = nodes
        self.edges = edges
        self.groups = groups or []
        self.project = project or {"Name":"", "Description":"", "ExcavationSite":""}
        self.selected_node = None; self.selected_group = None; self.selected_edge_index = None
        self.status.set(f"Loaded {len(nodes)} units and {len(edges)} relations")
        self.draw()
        self.validate(silent=True)

    # ---------- HMCX import/export ----------
    def open_hmcx(self):
        path = filedialog.askopenfilename(filetypes=[("Harris Matrix Composer files", "*.hmcx"), ("All files", "*.*")])
        if not path: return
        try:
            nodes, edges, groups, project = self.read_hmcx(path)
            self.filename = path
            self.import_loaded_data(nodes, edges, groups, project)
            self.fit_view()
            messagebox.showinfo("HMCX import", f"Imported {len(nodes)} units and {len(edges)} relations from:\n{path}")
        except Exception as e:
            messagebox.showerror("HMCX import failed", str(e))

    def read_hmcx(self, path):
        path = Path(path)
        with zipfile.ZipFile(path, "r") as z:
            names = z.namelist()
            if "matrix.xml" not in names:
                raise ValueError("This .hmcx file does not contain matrix.xml")
            matrix_xml = z.read("matrix.xml")
            project = {"Name":"", "Description":"", "ExcavationSite":""}
            if "project.xml" in names:
                try:
                    rootp = ET.fromstring(z.read("project.xml"))
                    project.update(rootp.attrib)
                except Exception:
                    pass
        root = ET.fromstring(matrix_xml)
        nodes = {}
        edges = []
        # real HMC stores hmcnode inside GraphML node/data with empty namespace
        for node in root.findall(".//g:node", NS):
            graph_id = node.get("id") or ""
            h = None
            for el in node.iter():
                if str(el.tag).split("}")[-1] == "hmcnode":
                    h = el; break
            if h is None:
                nid = graph_id
                attrs = {}
            else:
                attrs = dict(h.attrib)
                nid = attrs.get("id") or graph_id
            if not nid:
                continue
            typ = (attrs.get("type") or "UNKNOWN").upper()
            x = safe_float(attrs.get("x"), 50)
            y = safe_float(attrs.get("y"), 50)
            label = attrs.get("id") or nid
            name = attrs.get("name", "")
            if nid in ("T", "Top") and not name: name = "Top surface"
            if nid in ("G", "Geology") and not name: name = "Interface to Geology"
            if nid in ("U", "Unexcavated") and not name: name = "Unexcavated"
            nodes[nid] = {
                "id": nid,
                "label": label,
                "name": name,
                "description": attrs.get("description", ""),
                "type": typ,
                "layer": safe_int(attrs.get("layer"), 0),
                "index": safe_int(attrs.get("index"), 0),
                "x": x,
                "y": y,
                "valid": attrs.get("valid", "true").lower() != "false",
                "bookmarked": attrs.get("bookmarked", "false").lower() == "true",
            }
        for edge in root.findall(".//g:edge", NS):
            source = edge.get("source")
            target = edge.get("target")
            if not source or not target:
                continue
            h = None
            for el in edge.iter():
                if str(el.tag).split("}")[-1] == "hmcedge":
                    h = el; break
            attrs = dict(h.attrib) if h is not None else {}
            typ = (attrs.get("type") or EDGE_ABOVE).upper()
            if typ not in (EDGE_ABOVE, EDGE_LATER, EDGE_CONTEMP):
                typ = EDGE_ABOVE
            edges.append({
                "id": edge.get("id", f"e{len(edges)+1}"),
                "source": source,
                "target": target,
                "type": typ,
                "valid": attrs.get("valid", "true").lower() != "false",
            })
        if not nodes:
            raise ValueError("No HMC nodes found in matrix.xml")
        return nodes, edges, [], project

    def export_hmcx(self):
        path = filedialog.asksaveasfilename(defaultextension=".hmcx", filetypes=[("HMCX", "*.hmcx")])
        if not path: return
        try:
            self.write_hmcx(path)
            messagebox.showinfo("Export HMCX", path)
        except Exception as e:
            messagebox.showerror("Export HMCX failed", str(e))

    def write_hmcx(self, path):
        graph_attrs = f'edgedefault="directed" id="g1" parse.edges="{len(self.edges)}" parse.nodes="{len(self.nodes)}" parse.order="free"'
        parts = ['<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
                 f'<graphml xmlns="{GRAPHML_NS}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
                 '<key extension.type="hmc" for="node" id="d0"/>',
                 '<key extension.type="hmc" for="edge" id="d1"/>',
                 '<key extension.type="hmc" for="graph" id="d2"/>',
                 f'<graph {graph_attrs}>']
        for idx,n in enumerate(self.nodes.values()):
            nid = n.get("id", "")
            parts.append(f'<node id="{xml_escape(nid)}"><data key="d2"><hmcnode bookmarked="{str(n.get("bookmarked",False)).lower()}" description="{xml_escape(n.get("description",""))}" id="{xml_escape(nid)}" index="{idx}" layer="{int(n.get("layer",0))}" name="{xml_escape(n.get("name",""))}" type="{xml_escape(n.get("type","UNKNOWN"))}" valid="{str(n.get("valid",True)).lower()}" x="{float(n.get("x",0))}" y="{float(n.get("y",0))}" xmlns=""/></data></node>')
        for idx,e in enumerate(self.edges, start=1):
            eid = e.get("id") or f"e{idx}"
            parts.append(f'<edge id="{xml_escape(eid)}" source="{xml_escape(e.get("source",""))}" target="{xml_escape(e.get("target",""))}"><data key="d1"><hmcedge type="{xml_escape(e.get("type",EDGE_ABOVE))}" valid="{str(e.get("valid",True)).lower()}" xmlns=""/></data></edge>')
        parts += ['</graph>', '</graphml>']
        project = f'<?xml version="1.0" ?><ProjectProperties Name="{xml_escape(self.project.get("Name",""))}" Description="{xml_escape(self.project.get("Description",""))}" ExcavationSite="{xml_escape(self.project.get("ExcavationSite",""))}"></ProjectProperties>'
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("project.xml", project)
            z.writestr("matrix.xml", "\n".join(parts))

    # ---------- JSON ----------
    def open_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path: return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.nodes = {n["id"]: n for n in data.get("nodes", [])}
        self.edges = data.get("edges", [])
        self.groups = data.get("groups", [])
        self.project = data.get("project", {"Name":"", "Description":"", "ExcavationSite":""})
        self.filename=path
        self.draw(); self.fit_view()

    def save_json(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path: return
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"project":self.project, "nodes":list(self.nodes.values()), "edges":self.edges, "groups":self.groups}, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("Saved", path)

    # ---------- Canvas draw ----------
    def draw(self):
        self.canvas.delete("all")
        # groups behind lines and nodes
        for i,g in enumerate(self.groups):
            self.draw_group(i,g)
        for i,e in enumerate(self.edges):
            if e.get("type") in (EDGE_LATER, EDGE_CONTEMP) and not self.show_temporal.get():
                continue
            self.draw_edge(i,e)
        for n in self.nodes.values():
            self.draw_node(n)
        self.draw_legend()
        self.update_inspector()

    def draw_group(self, i, g):
        x,y,w,h = self.sx(g.get("x",0)), self.sy(g.get("y",0)), self.sx(g.get("w",100)), self.sy(g.get("h",100))
        outline = "#AA6A00" if g.get("kind","phase").lower()=="period" else "#276EB5"
        if i == self.selected_group: outline = "red"
        if g.get("collapsed"):
            self.canvas.create_rectangle(x,y,x+self.sx(120),y+self.sy(38), fill="#F4F4F4", outline=outline, width=2, tags=("group",str(i)))
            self.canvas.create_text(x+self.sx(60), y+self.sy(19), text=g.get("name","Group"), font=("Arial",9,"bold"), tags=("group",str(i)))
        else:
            self.canvas.create_rectangle(x,y,x+w,y+h, outline=outline, width=2, dash=(6,4), tags=("group",str(i)))
            self.canvas.create_text(x+self.sx(8), y+self.sy(15), text=g.get("name","Group"), anchor="w", fill=outline, font=("Arial",10,"bold"), tags=("group",str(i)))
            self.canvas.create_rectangle(x+w-self.sx(10), y+h-self.sy(10), x+w+self.sx(2), y+h+self.sy(2), fill=outline, outline="", tags=("gresize",str(i)))

    def draw_node(self, n):
        x,y = self.sx(n.get("x",0)), self.sy(n.get("y",0))
        w,h = self.sx(n.get("w",BOX_W)), self.sy(n.get("h",BOX_H))
        typ = n.get("type","UNKNOWN").upper()
        fill, shape = TYPE_STYLE.get(typ, TYPE_STYLE["UNKNOWN"])
        outline = "red" if n.get("id") == self.selected_node else ("#555" if n.get("valid",True) else "#D00000")
        tags = ("node", n.get("id",""))
        if shape == "oval":
            self.canvas.create_oval(x,y,x+w,y+h, fill=fill, outline=outline, width=2, tags=tags)
        else:
            self.canvas.create_rectangle(x,y,x+w,y+h, fill=fill, outline=outline, width=2, tags=tags)
        label = n.get("label") or n.get("id")
        self.canvas.create_text(x+w/2, y+h/2, text=label, font=("Arial",9,"bold"), tags=tags)
        if self.show_invalid.get() and not n.get("valid", True):
            self.canvas.create_text(x+w+self.sx(8), y+h/2, text="!", fill="#D00000", font=("Arial",14,"bold"))

    def draw_edge(self, index, e):
        s,t = e.get("source"), e.get("target")
        if s not in self.nodes or t not in self.nodes: return
        a,b = self.nodes[s], self.nodes[t]
        aw,ah = a.get("w",BOX_W), a.get("h",BOX_H)
        bw,bh = b.get("w",BOX_W), b.get("h",BOX_H)
        typ = e.get("type",EDGE_ABOVE).upper()
        color = "#7A1FA2" if typ in (EDGE_LATER, EDGE_CONTEMP) else "black"
        if not e.get("valid", True): color = "#D00000"
        width = 3 if index == self.selected_edge_index else 2
        dash = (4,3) if typ in (EDGE_LATER, EDGE_CONTEMP) else None
        if typ == EDGE_CONTEMP:
            x1,y1 = a["x"]+aw, a["y"]+ah/2
            x2,y2 = b["x"], b["y"]+bh/2
            self.canvas.create_line(self.sx(x1),self.sy(y1),self.sx(x2),self.sy(y2), fill=color, width=width, dash=dash, arrow=tk.BOTH, tags=("edge",str(index)))
        else:
            x1,y1 = a["x"]+aw/2, a["y"]+ah
            x2,y2 = b["x"]+bw/2, b["y"]
            mid = (y1+y2)/2
            self.canvas.create_line(self.sx(x1),self.sy(y1),self.sx(x1),self.sy(mid),self.sx(x2),self.sy(mid),self.sx(x2),self.sy(y2), fill=color, width=width, dash=dash, arrow=tk.LAST, tags=("edge",str(index)))

    def draw_legend(self):
        x,y=20,20
        self.canvas.create_rectangle(self.sx(x-10),self.sy(y-10),self.sx(x+235),self.sy(y+180),fill="white",outline="#ccc")
        self.canvas.create_text(self.sx(x),self.sy(y),text="Harris Matrix Editor 6",anchor="nw",font=("Arial",11,"bold"))
        items=[("Surface / interface", "#7ECF73"), ("Deposit / structure", "#8DBBE8"), ("Unexcavated", "#CFCFCF"), ("Temporal relation", "#7A1FA2"), ("Invalid", "#D00000")]
        for i,(name,col) in enumerate(items):
            yy=y+28+i*26
            self.canvas.create_rectangle(self.sx(x),self.sy(yy),self.sx(x+22),self.sy(yy+15),fill=col,outline="black")
            self.canvas.create_text(self.sx(x+30),self.sy(yy+8),text=name,anchor="w",font=("Arial",9))

    # ---------- Mouse ----------
    def hit_test(self, event):
        x,y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        for item in reversed(self.canvas.find_overlapping(x,y,x,y)):
            tags = self.canvas.gettags(item)
            if "node" in tags:
                for t in tags:
                    if t in self.nodes: return ("node", t)
            if "gresize" in tags:
                for t in tags:
                    if t.isdigit(): return ("gresize", int(t))
            if "group" in tags:
                for t in tags:
                    if t.isdigit(): return ("group", int(t))
            if "edge" in tags:
                for t in tags:
                    if t.isdigit(): return ("edge", int(t))
        return (None,None)

    def on_press(self, event):
        kind, val = self.hit_test(event)
        self.selected_node=None; self.selected_group=None; self.selected_edge_index=None; self.drag_mode=None
        x,y = self.ux(self.canvas.canvasx(event.x)), self.uy(self.canvas.canvasy(event.y))
        if kind == "node":
            self.selected_node = val
            n = self.nodes[val]
            self.drag = (x-n.get("x",0), y-n.get("y",0)); self.drag_mode="node"
        elif kind == "gresize":
            self.selected_group = val
            g = self.groups[val]
            self.drag = (x-(g.get("x",0)+g.get("w",100)), y-(g.get("y",0)+g.get("h",100))); self.drag_mode="resize_group"
        elif kind == "group":
            self.selected_group = val
            g = self.groups[val]
            self.drag = (x-g.get("x",0), y-g.get("y",0)); self.drag_mode="move_group"
        elif kind == "edge":
            self.selected_edge_index = val
        self.draw()

    def on_drag(self, event):
        x,y = self.ux(self.canvas.canvasx(event.x)), self.uy(self.canvas.canvasy(event.y))
        dx,dy = self.drag
        if self.drag_mode == "node" and self.selected_node:
            n = self.nodes[self.selected_node]
            n["x"] = round(x-dx,1); n["y"] = round(y-dy,1)
        elif self.drag_mode == "move_group" and self.selected_group is not None:
            g = self.groups[self.selected_group]
            g["x"] = round(x-dx,1); g["y"] = round(y-dy,1)
        elif self.drag_mode == "resize_group" and self.selected_group is not None:
            g = self.groups[self.selected_group]
            g["w"] = max(60, round(x-dx-g.get("x",0),1)); g["h"] = max(45, round(y-dy-g.get("y",0),1))
        self.draw()

    def on_release(self, event):
        self.drag_mode=None

    def on_double(self, event):
        kind, val = self.hit_test(event)
        if kind == "node":
            self.edit_node(val)
        elif kind == "group":
            self.edit_group(val)

    def pan_start(self, event): self.canvas.scan_mark(event.x, event.y)
    def pan_move(self, event): self.canvas.scan_dragto(event.x, event.y, gain=1)
    def on_wheel(self, event): self.set_zoom(self.zoom*(1.1 if event.delta>0 else 1/1.1))

    # ---------- Inspector ----------
    def update_inspector(self):
        self.props.delete("1.0", tk.END)
        if self.selected_node and self.selected_node in self.nodes:
            n = self.nodes[self.selected_node]
            text = "\n".join(f"{k}={n.get(k,'')}" for k in ["id","label","name","type","description","layer","x","y","valid"])
            self.props.insert("1.0", text)
        elif self.selected_group is not None and 0 <= self.selected_group < len(self.groups):
            g = self.groups[self.selected_group]
            text = "\n".join(f"{k}={g.get(k,'')}" for k in ["name","kind","members","collapsed","x","y","w","h"])
            self.props.insert("1.0", text)
        self.rel_list.delete(0, tk.END)
        if self.selected_node:
            for i,e in enumerate(self.edges):
                if e.get("source") == self.selected_node or e.get("target") == self.selected_node:
                    self.rel_list.insert(tk.END, f"{i}: {e.get('source')} -> {e.get('target')} [{e.get('type')}]")

    def apply_properties(self):
        lines = self.props.get("1.0", tk.END).splitlines()
        data = {}
        for line in lines:
            if "=" in line:
                k,v = line.split("=",1); data[k.strip()] = v.strip()
        if self.selected_node and self.selected_node in self.nodes:
            n = self.nodes[self.selected_node]
            old_id = n["id"]
            new_id = data.get("id", old_id)
            if new_id != old_id:
                if new_id in self.nodes:
                    messagebox.showerror("ID error", "That ID already exists")
                    return
                self.nodes[new_id] = self.nodes.pop(old_id)
                n = self.nodes[new_id]
                n["id"] = new_id
                for e in self.edges:
                    if e.get("source") == old_id: e["source"] = new_id
                    if e.get("target") == old_id: e["target"] = new_id
                self.selected_node = new_id
            for k,v in data.items():
                if k in ("x","y","layer"):
                    n[k] = safe_float(v) if k in ("x","y") else safe_int(v)
                elif k == "valid":
                    n[k] = v.lower() not in ("false","0","no")
                else:
                    n[k] = v
        elif self.selected_group is not None and 0 <= self.selected_group < len(self.groups):
            g = self.groups[self.selected_group]
            for k,v in data.items():
                if k in ("x","y","w","h"):
                    g[k] = safe_float(v)
                elif k == "collapsed":
                    g[k] = v.lower() in ("true","1","yes")
                else:
                    g[k] = v
        self.draw()

    def relation_select(self, event=None):
        sel = self.rel_list.curselection()
        if not sel: return
        line = self.rel_list.get(sel[0])
        try:
            self.selected_edge_index = int(line.split(":",1)[0])
        except Exception:
            return
        self.draw()

    # ---------- Editing ----------
    def add_node_dialog(self, typ):
        nid = simpledialog.askstring("New unit", "Unit ID:", parent=self)
        if not nid: return
        if nid in self.nodes:
            messagebox.showerror("Error", "ID already exists")
            return
        self.nodes[nid] = {"id":nid, "label":nid, "name":"", "description":"", "type":typ, "layer":0, "x":300, "y":80, "valid":False}
        self.draw()

    def edit_node(self, nid):
        n = self.nodes[nid]
        label = simpledialog.askstring("Label", "Label:", initialvalue=n.get("label",nid), parent=self)
        if label is None: return
        typ = simpledialog.askstring("Type", "SURFACE / DEPOSIT / CUT / FILL / STRUCTURAL:", initialvalue=n.get("type","SURFACE"), parent=self)
        if typ is None: return
        desc = simpledialog.askstring("Description", "Description:", initialvalue=n.get("description",""), parent=self)
        n["label"], n["type"], n["description"] = label, typ.upper(), desc or ""
        self.draw()

    def add_relation_dialog(self, typ):
        a = simpledialog.askstring("Relation", "Source / younger / above:", parent=self)
        b = simpledialog.askstring("Relation", "Target / older / below:", parent=self)
        if not a or not b: return
        ok,msg = self.add_edge_checked(a.strip(), b.strip(), typ)
        if not ok: messagebox.showwarning("Relation", msg)
        self.draw()

    def add_edge_checked(self, source, target, typ=EDGE_ABOVE):
        if source == target:
            return False, "A unit cannot relate to itself"
        if source not in self.nodes: self.nodes[source] = {"id":source,"label":source,"type":"UNKNOWN","x":300,"y":80,"valid":False}
        if target not in self.nodes: self.nodes[target] = {"id":target,"label":target,"type":"UNKNOWN","x":300,"y":80,"valid":False}
        if any(e.get("source")==source and e.get("target")==target and e.get("type")==typ for e in self.edges):
            return False, "Relation already exists"
        if typ in (EDGE_ABOVE, EDGE_LATER) and self.creates_cycle(source,target):
            return False, "Relation creates a cycle"
        eid = f"e{len(self.edges)+1}"
        self.edges.append({"id":eid,"source":source,"target":target,"type":typ,"valid":True})
        return True, "OK"

    def add_group_dialog(self):
        name = simpledialog.askstring("Phase/period box", "Name:", parent=self)
        if not name: return
        members = simpledialog.askstring("Members", "Unit IDs separated by comma:", parent=self) or ""
        self.groups.append({"name":name,"kind":"phase","members":members,"collapsed":False,"x":250,"y":250,"w":350,"h":160})
        self.draw()

    def edit_group(self, idx):
        g = self.groups[idx]
        name = simpledialog.askstring("Group", "Name:", initialvalue=g.get("name",""), parent=self)
        if name is not None: g["name"] = name
        members = simpledialog.askstring("Members", "Unit IDs separated by comma:", initialvalue=g.get("members",""), parent=self)
        if members is not None: g["members"] = members
        self.draw()

    def toggle_group(self):
        if self.selected_group is None:
            messagebox.showinfo("Collapse", "Select a group box first")
            return
        self.groups[self.selected_group]["collapsed"] = not self.groups[self.selected_group].get("collapsed",False)
        self.draw()

    def delete_selected_relation(self):
        if self.selected_edge_index is not None and 0 <= self.selected_edge_index < len(self.edges):
            del self.edges[self.selected_edge_index]
            self.selected_edge_index=None
            self.draw()

    # ---------- Validation/layout ----------
    def graph_for_order(self, include_temporal=True):
        edges=[]
        for e in self.edges:
            typ=e.get("type",EDGE_ABOVE).upper()
            if typ == EDGE_CONTEMP: continue
            if typ == EDGE_LATER and not include_temporal: continue
            edges.append((e.get("source"), e.get("target")))
        return edges

    def creates_cycle(self, source, target):
        g = defaultdict(list)
        for a,b in self.graph_for_order(True): g[a].append(b)
        g[source].append(target)
        stack=[target]; seen=set()
        while stack:
            n=stack.pop()
            if n == source: return True
            if n in seen: continue
            seen.add(n)
            stack += g.get(n,[])
        return False

    def validate(self, silent=False):
        problems=[]; warnings=[]
        for n in self.nodes.values(): n["valid"] = True
        # references
        for e in self.edges:
            if e.get("source") not in self.nodes:
                problems.append(f"Missing source node: {e.get('source')}")
            if e.get("target") not in self.nodes:
                problems.append(f"Missing target node: {e.get('target')}")
        # cycles
        g=defaultdict(list)
        for a,b in self.graph_for_order(True): g[a].append(b)
        temp=set(); perm=set()
        def visit(n,path):
            if n in temp:
                problems.append("Cycle: " + " -> ".join(path+[n])); return
            if n in perm: return
            temp.add(n)
            for m in g.get(n,[]): visit(m,path+[n])
            temp.remove(n); perm.add(n)
        for n in self.nodes: visit(n,[])
        # HMC validity: non-boundary units should normally have at least one relation above and below
        incoming=defaultdict(int); outgoing=defaultdict(int)
        for e in self.edges:
            if e.get("type") in (EDGE_ABOVE, EDGE_LATER):
                outgoing[e.get("source")]+=1; incoming[e.get("target")]+=1
        for nid,n in self.nodes.items():
            typ=n.get("type","UNKNOWN").upper()
            if typ not in ("TOP_SURFACE","GEOLOGY"):
                if incoming[nid]==0:
                    warnings.append(f"{nid}: no unit above / younger relation")
                    n["valid"] = False
                if outgoing[nid]==0:
                    warnings.append(f"{nid}: no unit below / older relation")
                    n["valid"] = False
            if typ == "UNKNOWN":
                warnings.append(f"{nid}: unknown type")
                n["valid"] = False
        for e in self.edges:
            if e.get("target") in ("T","Top"):
                problems.append("Nothing should be above the top surface")
            if e.get("source") in ("G","Geology"):
                problems.append("Geology/interface should not be above another unit")
        if silent:
            self.status.set(f"Validation: {len(problems)} errors, {len(warnings)} warnings")
            self.draw()
            return problems,warnings
        self.msg_list.delete(0,tk.END)
        for p in problems: self.msg_list.insert(tk.END, "ERROR: "+p)
        for w in warnings: self.msg_list.insert(tk.END, "WARN: "+w)
        self.status.set(f"Validation: {len(problems)} errors, {len(warnings)} warnings")
        self.draw()
        return problems,warnings

    def validate_show(self):
        p,w = self.validate(silent=False)
        if not p and not w:
            messagebox.showinfo("Validate", "✓ Matrix is valid")
        else:
            messagebox.showwarning("Validate", f"{len(p)} errors, {len(w)} warnings. See message list.")

    def remove_transitive_edges(self):
        order_edges = [e for e in self.edges if e.get("type") in (EDGE_ABOVE, EDGE_LATER)]
        keep = [e for e in self.edges if e.get("type") == EDGE_CONTEMP]
        g=defaultdict(list)
        for e in order_edges: g[e["source"]].append(e["target"])
        removed=0
        for e in order_edges:
            a,b=e["source"],e["target"]
            redundant=False
            for mid in g[a]:
                if mid == b: continue
                stack=[mid]; seen=set()
                while stack:
                    x=stack.pop()
                    if x == b:
                        redundant=True; break
                    if x in seen: continue
                    seen.add(x); stack += g.get(x,[])
                if redundant: break
            if redundant: removed+=1
            else: keep.append(e)
        self.edges=keep
        self.status.set(f"Removed {removed} transitive/redundant relation(s)")
        self.draw()

    def auto_layout(self):
        problems,_ = self.validate(silent=True)
        if problems:
            messagebox.showerror("Auto layout", "Fix errors/cycles before applying layout")
            return
        self.remove_transitive_edges()
        edges = self.graph_for_order(include_temporal=True)
        children=defaultdict(list); indeg={n:0 for n in self.nodes}
        for a,b in edges:
            children[a].append(b); indeg[b]=indeg.get(b,0)+1; indeg.setdefault(a,0)
        q=deque([n for n,d in indeg.items() if d==0])
        level={n:0 for n in self.nodes}
        while q:
            n=q.popleft()
            for m in children.get(n,[]):
                level[m]=max(level.get(m,0),level[n]+1)
                indeg[m]-=1
                if indeg[m]==0: q.append(m)
        # contemporary must share same layer
        for e in self.edges:
            if e.get("type") == EDGE_CONTEMP:
                a,b=e.get("source"),e.get("target")
                lv=max(level.get(a,0), level.get(b,0))
                level[a]=level[b]=lv
        max_layer = max(level.values()) if level else 0
        for nid,n in self.nodes.items():
            typ=n.get("type","UNKNOWN").upper()
            if typ == "TOP_SURFACE" or nid in ("T","Top"):
                level[nid] = 0
            elif typ == "GEOLOGY" or nid in ("G","Geology"):
                level[nid] = max_layer + 2
            elif typ == "UNEXCAVATED" or nid in ("U","Unexcavated"):
                level[nid] = max_layer + 1
        buckets=defaultdict(list)
        for nid in self.nodes: buckets[level.get(nid,0)].append(nid)
        def sort_key(nid):
            # preserve HMC index/order where possible
            return (safe_int(self.nodes[nid].get("index"), 9999), self.primary_number(nid), nid)
        for layer in sorted(buckets):
            arr=sorted(buckets[layer], key=sort_key)
            for i,nid in enumerate(arr):
                self.nodes[nid]["layer"] = layer
                self.nodes[nid]["x"] = 300 + i*COL_X
                self.nodes[nid]["y"] = 60 + layer*LAYER_Y
        self.fit_groups_to_members()
        self.draw(); self.fit_view()
        self.status.set(f"Auto layout applied to {len(self.nodes)} units")

    def primary_number(self, s):
        m=re.search(r"\d+", str(s))
        return int(m.group()) if m else 999999

    def fit_groups_to_members(self):
        for g in self.groups:
            members = [m.strip() for m in str(g.get("members","")).split(",") if m.strip() in self.nodes]
            if not members: continue
            ns=[self.nodes[m] for m in members]
            minx=min(n["x"] for n in ns)-35; miny=min(n["y"] for n in ns)-45
            maxx=max(n["x"]+n.get("w",BOX_W) for n in ns)+35; maxy=max(n["y"]+n.get("h",BOX_H) for n in ns)+35
            g.update({"x":minx,"y":miny,"w":maxx-minx,"h":maxy-miny})

    # ---------- Search/navigation ----------
    def search_dialog(self):
        q = simpledialog.askstring("Search", "Search ID/name/description:", parent=self)
        if not q: return
        self.msg_list.delete(0,tk.END)
        ql=q.lower(); count=0
        for nid,n in self.nodes.items():
            hay=" ".join(str(n.get(k,"")) for k in ["id","label","name","description","type"]).lower()
            if ql in hay:
                self.msg_list.insert(tk.END, "FOUND: "+nid)
                count += 1
        self.status.set(f"Search found {count} unit(s)")

    def message_double_click(self, event=None):
        sel=self.msg_list.curselection()
        if not sel: return
        text=self.msg_list.get(sel[0])
        for nid in self.nodes:
            if nid in text:
                self.focus_node(nid); return

    def focus_node(self, nid):
        if nid not in self.nodes: return
        n=self.nodes[nid]
        self.selected_node=nid
        self.canvas.xview_moveto(max(0, self.sx(n["x"]-400)/4200))
        self.canvas.yview_moveto(max(0, self.sy(n["y"]-250)/3200))
        self.draw()

    def fit_view(self):
        if not self.nodes: return
        xs=[]; ys=[]
        for n in self.nodes.values():
            xs += [n.get("x",0), n.get("x",0)+n.get("w",BOX_W)]
            ys += [n.get("y",0), n.get("y",0)+n.get("h",BOX_H)]
        minx,miny,maxx,maxy=min(xs),min(ys),max(xs),max(ys)
        cw=max(1,self.canvas.winfo_width()); ch=max(1,self.canvas.winfo_height())
        self.zoom=max(0.25,min(2.5, min((cw-80)/max(1,maxx-minx), (ch-80)/max(1,maxy-miny))))
        self.draw()
        self.canvas.xview_moveto(max(0,self.sx(minx-40)/4200))
        self.canvas.yview_moveto(max(0,self.sy(miny-40)/3200))

    def set_zoom(self, z):
        self.zoom=max(0.2,min(3.5,z))
        self.draw()
        self.status.set(f"Zoom {self.zoom:.2f}")

    # ---------- Export ----------
    def export_svg(self):
        path = filedialog.asksaveasfilename(defaultextension=".svg", filetypes=[("SVG", "*.svg")])
        if not path: return
        Path(path).write_text(self.make_svg(), encoding="utf-8")
        messagebox.showinfo("SVG", path)

    def make_svg(self):
        xs=[]; ys=[]
        for n in self.nodes.values():
            xs += [n.get("x",0), n.get("x",0)+n.get("w",BOX_W)]
            ys += [n.get("y",0), n.get("y",0)+n.get("h",BOX_H)]
        W=max(1200, int(max(xs+[100])+120)); H=max(900, int(max(ys+[100])+120))
        parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">','<rect width="100%" height="100%" fill="white"/>']
        for e in self.edges:
            if e.get("source") not in self.nodes or e.get("target") not in self.nodes: continue
            a,b=self.nodes[e["source"]],self.nodes[e["target"]]
            aw,ah=a.get("w",BOX_W),a.get("h",BOX_H); bw,bh=b.get("w",BOX_W),b.get("h",BOX_H)
            typ=e.get("type",EDGE_ABOVE)
            col="#7A1FA2" if typ in (EDGE_LATER,EDGE_CONTEMP) else "black"
            dash=' stroke-dasharray="4 3"' if typ in (EDGE_LATER,EDGE_CONTEMP) else ""
            if typ==EDGE_CONTEMP:
                x1,y1=a["x"]+aw,a["y"]+ah/2; x2,y2=b["x"],b["y"]+bh/2
                parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="2"{dash}/>')
            else:
                x1,y1=a["x"]+aw/2,a["y"]+ah; x2,y2=b["x"]+bw/2,b["y"]; mid=(y1+y2)/2
                parts.append(f'<polyline points="{x1},{y1} {x1},{mid} {x2},{mid} {x2},{y2}" fill="none" stroke="{col}" stroke-width="2"{dash}/>')
        for n in self.nodes.values():
            x,y,w,h=n.get("x",0),n.get("y",0),n.get("w",BOX_W),n.get("h",BOX_H)
            fill,shape=TYPE_STYLE.get(n.get("type","UNKNOWN").upper(),TYPE_STYLE["UNKNOWN"])
            if shape=="oval": parts.append(f'<ellipse cx="{x+w/2}" cy="{y+h/2}" rx="{w/2}" ry="{h/2}" fill="{fill}" stroke="black" stroke-width="1.5"/>')
            else: parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="black" stroke-width="1.5"/>')
            parts.append(f'<text x="{x+w/2}" y="{y+h/2+4}" text-anchor="middle" font-family="Arial" font-size="12" font-weight="bold">{xml_escape(n.get("label",n.get("id","")))}</text>')
        parts.append('</svg>')
        return "\n".join(parts)

    def export_pdf(self):
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not path: return
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A3, landscape
            from reportlab.lib.colors import HexColor, black
            c=canvas.Canvas(path, pagesize=landscape(A3))
            pw,ph=landscape(A3)
            xs=[]; ys=[]
            for n in self.nodes.values(): xs += [n.get("x",0),n.get("x",0)+n.get("w",BOX_W)]; ys += [n.get("y",0),n.get("y",0)+n.get("h",BOX_H)]
            minx,miny,maxx,maxy=min(xs+[0])-60,min(ys+[0])-60,max(xs+[100])+60,max(ys+[100])+60
            scale=min((pw-50)/(maxx-minx),(ph-50)/(maxy-miny))
            def tx(x): return 25+(x-minx)*scale
            def ty(y): return ph-(25+(y-miny)*scale)
            c.setTitle("Harris Matrix")
            for e in self.edges:
                if e.get("source") not in self.nodes or e.get("target") not in self.nodes: continue
                a,b=self.nodes[e["source"]],self.nodes[e["target"]]
                aw,ah=a.get("w",BOX_W),a.get("h",BOX_H); bw,bh=b.get("w",BOX_W),b.get("h",BOX_H)
                if e.get("type") in (EDGE_LATER,EDGE_CONTEMP): c.setDash(3,3)
                else: c.setDash()
                x1,y1=a["x"]+aw/2,a["y"]+ah; x2,y2=b["x"]+bw/2,b["y"]; mid=(y1+y2)/2
                for (xa,ya),(xb,yb) in zip([(x1,y1),(x1,mid),(x2,mid)],[(x1,mid),(x2,mid),(x2,y2)]): c.line(tx(xa),ty(ya),tx(xb),ty(yb))
            c.setDash()
            for n in self.nodes.values():
                x,y,w,h=n.get("x",0),n.get("y",0),n.get("w",BOX_W),n.get("h",BOX_H)
                fill,_=TYPE_STYLE.get(n.get("type","UNKNOWN").upper(),TYPE_STYLE["UNKNOWN"])
                c.setFillColor(HexColor(fill)); c.rect(tx(x),ty(y+h),w*scale,h*scale,fill=1,stroke=1)
                c.setFillColor(black); c.drawCentredString(tx(x+w/2),ty(y+h/2)+3,n.get("label",n.get("id",""))[:24])
            c.save(); messagebox.showinfo("PDF", path)
        except Exception as e:
            messagebox.showerror("PDF export failed", str(e))

if __name__ == "__main__":
    HarrisMatrixEditor().mainloop()
