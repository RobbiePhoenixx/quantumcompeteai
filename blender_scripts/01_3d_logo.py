"""
3D Logo Generator
=================
Ask Claude: "Make me a 3D logo that says [YOUR BUSINESS NAME]"
Then run this script inside Blender: Scripting tab → Run Script

What this does: Creates bold 3D text with a gold material,
ready to render as a product visual or social media asset.
"""

import bpy

# ── Clean the scene ──────────────────────────────────────────────────────────
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# ── Create 3D text ───────────────────────────────────────────────────────────
bpy.ops.object.text_add(location=(0, 0, 0))
text_obj = bpy.context.object
text_obj.data.body = "QUANTUM\nCOMPETE AI"
text_obj.data.align_x = 'CENTER'
text_obj.data.align_y = 'CENTER'
text_obj.data.size = 1.2
text_obj.data.extrude = 0.15          # gives it depth (the 3D part)
text_obj.data.bevel_depth = 0.02      # rounds the edges
text_obj.data.bevel_resolution = 4

# ── Gold material ─────────────────────────────────────────────────────────────
mat = bpy.data.materials.new(name="Gold")
mat.use_nodes = True
nodes = mat.node_tree.nodes
bsdf = nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value  = (0.8, 0.6, 0.1, 1.0)
    bsdf.inputs["Metallic"].default_value    = 1.0
    bsdf.inputs["Roughness"].default_value   = 0.2
text_obj.data.materials.append(mat)

# ── Camera ────────────────────────────────────────────────────────────────────
bpy.ops.object.camera_add(location=(0, -6, 2))
cam = bpy.context.object
cam.rotation_euler = (1.2, 0, 0)
bpy.context.scene.camera = cam

# ── Light ─────────────────────────────────────────────────────────────────────
bpy.ops.object.light_add(type='SUN', location=(4, -4, 8))
bpy.context.object.data.energy = 5

print("3D logo created! Go to Render > Render Image to export.")
