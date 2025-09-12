bl_info = {
    "name": "NE-NOORE Tool",
    "author": "NOORE (built with Gemini & ChatGbt)",
    "version": (1, 8, 2),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > NE-NOORE",
    "description": "Prepare, material utilities, vertex color picker/apply, turbo texture finder, portal creator, and ymap utilities.",
    "category": "3D View",
}

import bpy
import os
import bmesh
from mathutils import Vector, Color, Quaternion
from bpy.props import (
    StringProperty, BoolProperty, FloatProperty, EnumProperty,
    PointerProperty, CollectionProperty, FloatVectorProperty, IntProperty
)
from bpy.types import Operator, Panel, PropertyGroup, Material

# -----------------------------
# Settings
# -----------------------------
class NENOORE_Settings(PropertyGroup):
    # Turbo finder
    turbo_root: StringProperty(name="Turbo Finder Root", subtype='DIR_PATH', default="")
    turbo_exts: StringProperty(name="Texture extensions (comma)", default="png,jpg,jpeg,tga,tif,tiff")
    show_turbo_settings: BoolProperty(default=False)

    # Vertex color store
    picked_color: FloatVectorProperty(name="Picked Color", subtype='COLOR', size=3, min=0.0, max=1.0, default=(1.0,1.0,1.0))

    # Material Utilities
    material_to_copy: PointerProperty(name="Material to Copy", type=bpy.types.Material)

# -----------------------------
# Portal item
# -----------------------------
class NENOORE_PortalCoord(PropertyGroup):
    coord: FloatVectorProperty(size=3, default=(0.0,0.0,0.0))

# -----------------------------
# Ymap props
# -----------------------------
class NENOORE_YmapProps(PropertyGroup):
    position: FloatVectorProperty(name="Position", size=3, default=(0.0, 0.0, 0.0), precision=6)
    rotation: FloatVectorProperty(name="Rotation", size=4, default=(0.0, 0.0, 0.0, 1.0), precision=6)


# -----------------------------
# Operators: Prepare
# -----------------------------
class NENOORE_OT_prepare_vanilla(Operator):
    bl_idname = "nenoore.prepare_vanilla"
    bl_label = "Prepare Vanilla Objects"
    bl_description = "Separate from parent and rename; optional: remove parent archetype"
    remove_parent: BoolProperty(default=False)

    def execute(self, context):
        prepared = 0
        sel = context.selected_objects[:]
        if not sel:
            self.report({'WARNING'}, "Select at least one object")
            return {'CANCELLED'}

        for obj in sel:
            if obj.type != 'MESH':
                continue
            
            # Get parent object before clearing parent
            parent_obj = obj.parent

            # Clear parent while keeping transform
            obj.select_set(True)
            context.view_layer.objects.active = obj
            try:
                bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
            except Exception:
                pass

            # Rename mesh data to object name to avoid .001 meshes
            if obj.data:
                obj.data.name = obj.name

            if self.remove_parent and parent_obj:
                # remove all other children of parent, keep current obj
                for child in list(parent_obj.children):
                    if child != obj:
                        try:
                            bpy.data.objects.remove(child, do_unlink=True)
                        except Exception:
                            pass
                try:
                    bpy.data.objects.remove(parent_obj, do_unlink=True)
                except Exception:
                    pass

            prepared += 1

        self.report({'INFO'}, f"Prepared {prepared} objects")
        return {'FINISHED'}


# -----------------------------
# Operators: Turbo Texture Finder
# -----------------------------
class NENOORE_OT_turbo_texture_finder(Operator):
    bl_idname = "nenoore.turbo_texture_finder"
    bl_label = "Turbo Texture Finder"
    bl_description = "Search folder recursively and relink missing textures"
    
    directory: StringProperty(subtype='DIR_PATH')
    
    def execute(self, context):
        root = bpy.path.abspath(self.directory)
        if not root or not os.path.isdir(root):
            self.report({'ERROR'}, "Selected path is not a valid directory.")
            return {'CANCELLED'}

        settings = context.scene.nenoore_settings
        exts_raw = settings.turbo_exts.split(',')
        exts = [e.strip().lower().lstrip('.') for e in exts_raw if e.strip()]
        
        filemap = {}
        for dirpath, _, filenames in os.walk(root):
            for f in filenames:
                ext = f.lower().split('.')[-1]
                if ext in exts:
                    key = f.lower()
                    if key not in filemap:
                        filemap[key] = os.path.join(dirpath, f)

        relinked = 0
        for img in bpy.data.images:
            if not img.filepath:
                continue
            abs_path = bpy.path.abspath(img.filepath)
            if not os.path.exists(abs_path):
                name = os.path.basename(img.filepath).lower()
                if name in filemap:
                    try:
                        img.filepath = bpy.path.relpath(filemap[name])
                        img.reload()
                        relinked += 1
                    except Exception:
                        pass

        self.report({'INFO'}, f"Turbo Finder: relinked {relinked} images")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class NENOORE_OT_toggle_turbo_settings(Operator):
    bl_idname = "nenoore.toggle_turbo_settings"
    bl_label = "Toggle Turbo Finder Settings"

    def execute(self, context):
        settings = context.scene.nenoore_settings
        settings.show_turbo_settings = not settings.show_turbo_settings
        return {'FINISHED'}


# -----------------------------
# Operators: Vertex Color Pick / Apply
# -----------------------------
class NENOORE_OT_pick_vertex_color(Operator):
    bl_idname = "nenoore.pick_vertex_color"
    bl_label = "Pick Vertex Color"
    bl_description = "Pick vertex color and copy its hex value to clipboard"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}

        # Ensure we have BMesh in edit mode to read selection
        if obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data)
        else:
            bm = bmesh.new()
            bm.from_mesh(obj.data)

        # find active color layer
        if not bm.loops.layers.color:
            if obj.mode != 'EDIT':
                bm.free()
            self.report({'ERROR'}, "Mesh has no vertex color layer")
            return {'CANCELLED'}
        color_layer = bm.loops.layers.color.active

        # collect colors from selected verts' loops
        sel_verts = [v for v in bm.verts if v.select]
        if not sel_verts:
            if obj.mode != 'EDIT':
                bm.free()
            self.report({'ERROR'}, "Select one or more vertices")
            return {'CANCELLED'}

        # average color across loops of selected vertices
        sumcol = Color((0.0,0.0,0.0))
        count = 0
        for v in sel_verts:
            for l in v.link_loops:
                col = l[color_layer]
                sumcol.r += col[0]; sumcol.g += col[1]; sumcol.b += col[2]
                count += 1

        if count == 0:
            if obj.mode != 'EDIT':
                bm.free()
            self.report({'ERROR'}, "Selected vertices don't have loop colors")
            return {'CANCELLED'}

        avg = Color((sumcol.r/count, sumcol.g/count, sumcol.b/count))
        # store in scene settings
        context.scene.nenoore_settings.picked_color = (avg.r, avg.g, avg.b)

        # Copy hex value to clipboard
        pr, pg, pb = context.scene.nenoore_settings.picked_color
        hexv = "#{:02X}{:02X}{:02X}".format(int(pr*255), int(pg*255), int(pb*255))
        context.window_manager.clipboard = hexv

        if obj.mode != 'EDIT':
            bm.free()
        self.report({'INFO'}, f"Picked color and copied hex: {hexv}")
        return {'FINISHED'}

class NENOORE_OT_apply_picked_color(Operator):
    bl_idname = "nenoore.apply_picked_color"
    bl_label = "Apply Picked Color"
    bl_description = "Apply stored picked color to selected vertices (creates layer if needed)"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        if obj.mode != 'EDIT':
            self.report({'ERROR'}, "Switch to Edit Mode to apply color")
            return {'CANCELLED'}

        bm = bmesh.from_edit_mesh(obj.data)
        color_layer = bm.loops.layers.color.active
        if not color_layer:
            # create a vertex color layer on the mesh
            color_layer = bm.loops.layers.color.new("Col")

        picked = context.scene.nenoore_settings.picked_color
        # make sure picked is a tuple of 3 floats
        if not picked:
            self.report({'ERROR'}, "No picked color stored")
            return {'CANCELLED'}
        pr, pg, pb = picked[0], picked[1], picked[2]

        sel_verts = [v for v in bm.verts if v.select]
        if not sel_verts:
            self.report({'ERROR'}, "Select one or more vertices to apply color")
            return {'CANCELLED'}

        for v in sel_verts:
            for l in v.link_loops:
                # We need to add an alpha value to fix the error.
                l[color_layer] = (pr, pg, pb, 1.0)

        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, "Applied picked color to selected vertices")
        return {'FINISHED'}


# -----------------------------
# Operators: Material Utilities
# -----------------------------
class NENOORE_OT_copy_material(Operator):
    bl_idname = "nenoore.copy_material"
    bl_label = "Copy Active Material"
    bl_description = "Copy the active material of the selected object"

    def execute(self, context):
        obj = context.active_object
        if not obj:
            self.report({'ERROR'}, "Select an object first.")
            return {'CANCELLED'}
        
        material_to_copy = obj.active_material

        if not material_to_copy:
            self.report({'ERROR'}, "Selected object does not have an active material.")
            return {'CANCELLED'}

        # Store the material in the scene settings
        context.scene.nenoore_settings.material_to_copy = material_to_copy

        self.report({'INFO'}, f"Copied material '{material_to_copy.name}'")
        return {'FINISHED'}


class NENOORE_OT_copy_material_name(Operator):
    bl_idname = "nenoore.copy_material_name"
    bl_label = "Copy Material Name"
    bl_description = "Copy the name of the stored material to the clipboard"

    def execute(self, context):
        settings = context.scene.nenoore_settings
        if not settings.material_to_copy:
            self.report({'ERROR'}, "No material has been copied yet.")
            return {'CANCELLED'}

        mat_name = settings.material_to_copy.name
        context.window_manager.clipboard = mat_name
        self.report({'INFO'}, f"Copied material name: '{mat_name}'")
        return {'FINISHED'}


class NENOORE_OT_apply_material(Operator):
    bl_idname = "nenoore.apply_material"
    bl_label = "Apply Material"
    bl_description = "Apply copied material to selected faces"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        if obj.mode != 'EDIT':
            self.report({'ERROR'}, "Switch to Edit Mode and select faces to apply material")
            return {'CANCELLED'}
        
        settings = context.scene.nenoore_settings
        material_to_apply = settings.material_to_copy

        if not material_to_apply:
            self.report({'ERROR'}, "No material has been copied yet")
            return {'CANCELLED'}
        
        bm = bmesh.from_edit_mesh(obj.data)
        selected_faces = [f for f in bm.faces if f.select]

        if not selected_faces:
            self.report({'ERROR'}, "Select at least one face to apply the material")
            bm.free()
            return {'CANCELLED'}
        
        # Check if the material already exists in the object's slots
        material_index = -1
        for i, slot in enumerate(obj.material_slots):
            if slot.material == material_to_apply:
                material_index = i
                break
        
        # If not, append it
        if material_index == -1:
            obj.data.materials.append(material_to_apply)
            material_index = len(obj.material_slots) - 1

        # Apply the material to all selected faces
        for face in selected_faces:
            face.material_index = material_index

        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, f"Applied material '{material_to_apply.name}' to {len(selected_faces)} faces")
        return {'FINISHED'}


# -----------------------------
# Operators: Portal Creator
# -----------------------------
class NENOORE_OT_add_portal_vertex(Operator):
    bl_idname = "nenoore.add_portal_vertex"
    bl_label = "Add Portal Vertex"
    bl_description = "Add currently selected vertex (edit mode) to portal list (world coords)"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        if obj.mode != 'EDIT':
            self.report({'ERROR'}, "Enter Edit Mode and select one vertex at a time")
            return {'CANCELLED'}

        bm = bmesh.from_edit_mesh(obj.data)
        sel_verts = [v for v in bm.verts if v.select]
        if len(sel_verts) != 1:
            self.report({'ERROR'}, "Select exactly one vertex at a time")
            return {'CANCELLED'}

        v = sel_verts[0]
        world_coord = obj.matrix_world @ v.co
        scene = context.scene
        coords = scene.nenoore_portal_coords
        if len(coords) >= 4:
            self.report({'WARNING'}, "Already have 4 vertices stored; reset first")
            return {'CANCELLED'}

        item = coords.add()
        item.coord = (world_coord.x, world_coord.y, world_coord.z)
        self.report({'INFO'}, f"Stored vertex {len(coords)}")
        return {'FINISHED'}


class NENOORE_OT_reset_portal(Operator):
    bl_idname = "nenoore.reset_portal"
    bl_label = "Reset Portal"
    bl_description = "Clear stored portal coordinates"

    def execute(self, context):
        context.scene.nenoore_portal_coords.clear()
        self.report({'INFO'}, "Portal coords cleared")
        return {'FINISHED'}


class NENOORE_OT_copy_single_coord(Operator):
    bl_idname = "nenoore.copy_single_coord"
    bl_label = "Copy Single Portal Coord"

    index: IntProperty()

    def execute(self, context):
        coords = context.scene.nenoore_portal_coords
        if self.index < 0 or self.index >= len(coords):
            self.report({'ERROR'}, "Invalid index")
            return {'CANCELLED'}
        x, y, z = coords[self.index].coord
        line = f"{x:.6f}, {y:.6f}, {z:.6f}"
        context.window_manager.clipboard = line
        self.report({'INFO'}, "Copied coordinate")
        return {'FINISHED'}


class NENOORE_OT_copy_all_coords(Operator):
    bl_idname = "nenoore.copy_all_coords"
    bl_label = "Copy All Portal Coords"

    def execute(self, context):
        coords = context.scene.nenoore_portal_coords
        if len(coords) != 4:
            self.report({'ERROR'}, "Need exactly 4 coords to copy all")
            return {'CANCELLED'}
        lines = []
        for item in coords:
            x, y, z = item.coord
            lines.append(f"{x:.6f}, {y:.6f}, {z:.6f}")
        text = "\n".join(lines)
        context.window_manager.clipboard = text
        self.report({'INFO'}, "Copied all portal coordinates")
        return {'FINISHED'}


# -----------------------------
# Operators: Ymap Utilities
# -----------------------------
class NENOORE_OT_get_ymap_coords(Operator):
    bl_idname = "nenoore.get_ymap_coords"
    bl_label = "Get YMAP Coords"
    bl_description = "Get position and rotation of the active object"

    def execute(self, context):
        obj = context.active_object
        if not obj:
            self.report({'ERROR'}, "Select an object")
            return {'CANCELLED'}

        # Get the world location and rotation (quaternion)
        world_pos = obj.matrix_world.translation
        world_rot_quat = obj.matrix_world.to_quaternion()

        # Store in the scene settings
        ymap_props = context.scene.nenoore_ymap_props
        ymap_props.position = world_pos
        ymap_props.rotation = world_rot_quat

        self.report({'INFO'}, "YMAP coords updated")
        return {'FINISHED'}

class NENOORE_OT_copy_ymap_position(Operator):
    bl_idname = "nenoore.copy_ymap_position"
    bl_label = "Copy Position"
    bl_description = "Copy the stored position to the clipboard"

    def execute(self, context):
        ymap_props = context.scene.nenoore_ymap_props
        x, y, z = ymap_props.position
        line = f"{x:.6f}, {y:.6f}, {z:.6f}"
        context.window_manager.clipboard = line
        self.report({'INFO'}, "Copied position")
        return {'FINISHED'}

class NENOORE_OT_copy_ymap_rotation(Operator):
    bl_idname = "nenoore.copy_ymap_rotation"
    bl_label = "Copy Rotation"
    bl_description = "Copy the stored rotation to the clipboard"

    def execute(self, context):
        ymap_props = context.scene.nenoore_ymap_props
        # GTA 5 uses a specific quaternion order, x, y, z, w
        # Blender's quaternion is w, x, y, z
        x, y, z, w = ymap_props.rotation[1], ymap_props.rotation[2], ymap_props.rotation[3], ymap_props.rotation[0]
        line = f"{x:.6f}, {y:.6f}, {z:.6f}, {w:.6f}"
        context.window_manager.clipboard = line
        self.report({'INFO'}, "Copied rotation")
        return {'FINISHED'}

class NENOORE_OT_copy_ymap_xml(Operator):
    bl_idname = "nenoore.copy_ymap_xml"
    bl_label = "Copy XML Format"
    bl_description = "Copy position and rotation in XML format for YMAPs"

    def execute(self, context):
        ymap_props = context.scene.nenoore_ymap_props
        pos_x, pos_y, pos_z = ymap_props.position
        # GTA 5 uses a specific quaternion order, x, y, z, w
        rot_x, rot_y, rot_z, rot_w = ymap_props.rotation[1], ymap_props.rotation[2], ymap_props.rotation[3], ymap_props.rotation[0]
        
        xml_string = (
            f'   <position x="{pos_x:.6f}" y="{pos_y:.6f}" z="{pos_z:.6f}" />\n'
            f'   <rotation x="{rot_x:.6f}" y="{rot_y:.6f}" z="{rot_z:.6f}" w="{rot_w:.6f}" />'
        )
        context.window_manager.clipboard = xml_string
        self.report({'INFO'}, "Copied YMAP XML to clipboard")
        return {'FINISHED'}


# -----------------------------
# UI Panels (collapsible style)
# -----------------------------
class NENOORE_PT_prepare(Panel):
    bl_label = "Prepare Objects"
    bl_idname = "NENOORE_PT_prepare"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'NE-NOORE'
    bl_icon = 'TOOL_SETTINGS'
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        layout = self.layout
        layout.label(text="", icon=self.bl_icon)

    def draw(self, context):
        layout = self.layout
        op = layout.operator("nenoore.prepare_vanilla", text="Prepare + Remove Parent")
        op.remove_parent = True
        op = layout.operator("nenoore.prepare_vanilla", text="Prepare (keep parent)")
        op.remove_parent = False


class NENOORE_PT_turbo(Panel):
    bl_label = "Turbo Texture Finder"
    bl_idname = "NENOORE_PT_turbo"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'NE-NOORE'
    bl_icon = 'IMAGE_DATA'
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        layout = self.layout
        layout.label(text="", icon=self.bl_icon)

    def draw(self, context):
        layout = self.layout
        settings = context.scene.nenoore_settings
        
        row = layout.row(align=True)
        # Main button to open file explorer
        row.operator("nenoore.turbo_texture_finder", text="Turbo Texture Finder", icon='IMAGE_DATA')
        # Button to toggle settings panel
        row.operator("nenoore.toggle_turbo_settings", text="", icon='SETTINGS')
        
        if settings.show_turbo_settings:
            box = layout.box()
            box.label(text="Image Extensions (comma separated)")
            box.prop(settings, "turbo_exts", text="e.g. dds, png, jpg")


class NENOORE_PT_material(Panel):
    bl_label = "Material Utilities"
    bl_idname = "NENOORE_PT_material"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'NE-NOORE'
    bl_icon = 'MATERIAL'
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        layout = self.layout
        layout.label(text="", icon=self.bl_icon)

    def draw(self, context):
        layout = self.layout
        layout.operator("nenoore.copy_material", text="Copy Active Material", icon='PASTEDOWN')
        layout.operator("nenoore.apply_material", text="Apply Material", icon='CHECKMARK')
        settings = context.scene.nenoore_settings
        if settings.material_to_copy:
            mat = settings.material_to_copy
            box = layout.box()
            row = box.row(align=True)
            row.label(text=f"Copied Material: {mat.name}")
            row.operator("nenoore.copy_material_name", text="", icon='COPYDOWN')


class NENOORE_PT_vertex_color(Panel):
    bl_label = "Vertex Color Picker"
    bl_idname = "NENOORE_PT_vertex_color"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'NE-NOORE'
    bl_icon = 'COLOR'
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        layout = self.layout
        layout.label(text="", icon=self.bl_icon)

    def draw(self, context):
        layout = self.layout
        settings = context.scene.nenoore_settings
        
        col = layout.column(align=True)
        col.operator("nenoore.pick_vertex_color", icon='EYEDROPPER')
        col.prop(settings, "picked_color", text="")
        col.operator("nenoore.apply_picked_color", icon='BRUSH_DATA', text="Apply Vertex Color")


class NENOORE_PT_portal(Panel):
    bl_label = "Portal Creator"
    bl_idname = "NENOORE_PT_portal"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'NE-NOORE'
    bl_icon = 'MOD_ARRAY'
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        layout = self.layout
        layout.label(text="", icon=self.bl_icon)

    def draw(self, context):
        layout = self.layout
        coords = context.scene.nenoore_portal_coords

        row = layout.row(align=True)
        row.operator("nenoore.add_portal_vertex", icon='ADD')
        
        for i, item in enumerate(coords):
            row = layout.row(align=True)
            row.label(text=f"{item.coord[0]:.6f}, {item.coord[1]:.6f}, {item.coord[2]:.6f}")
            op = row.operator("nenoore.copy_single_coord", text="", icon='COPYDOWN')
            op.index = i

        row = layout.row(align=True)
        row.operator("nenoore.reset_portal", icon='X')

        if len(coords) == 4:
            layout.operator("nenoore.copy_all_coords", icon='COPYDOWN')

class NENOORE_PT_ymap(Panel):
    bl_label = "YMAP Utilities"
    bl_idname = "NENOORE_PT_ymap"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'NE-NOORE'
    bl_icon = 'MESH_GRID'
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        layout = self.layout
        layout.label(text="", icon=self.bl_icon)

    def draw(self, context):
        layout = self.layout
        ymap_props = context.scene.nenoore_ymap_props

        layout.operator("nenoore.get_ymap_coords", icon='IMPORT')

        box = layout.box()
        col = box.column(align=True)
        
        # Position
        row = col.row(align=True)
        pos_x, pos_y, pos_z = ymap_props.position
        row.label(text=f"position: {pos_x:.6f}, {pos_y:.6f}, {pos_z:.6f}")
        row.operator("nenoore.copy_ymap_position", text="", icon='COPYDOWN')

        # Rotation
        row = col.row(align=True)
        # Blender's quaternion is w,x,y,z; GTA 5/CodeWalker uses x,y,z,w
        rot_x, rot_y, rot_z, rot_w = ymap_props.rotation[1], ymap_props.rotation[2], ymap_props.rotation[3], ymap_props.rotation[0]
        row.label(text=f"rotation: {rot_x:.6f}, {rot_y:.6f}, {rot_z:.6f}, {rot_w:.6f}")
        row.operator("nenoore.copy_ymap_rotation", text="", icon='COPYDOWN')
        
        # XML format
        layout.separator()
        layout.operator("nenoore.copy_ymap_xml", icon='FILE_TEXT')


# -----------------------------
# Register / unregister
# -----------------------------
classes = (
    NENOORE_Settings,
    NENOORE_PortalCoord,
    NENOORE_YmapProps,
    NENOORE_OT_prepare_vanilla,
    NENOORE_OT_turbo_texture_finder,
    NENOORE_OT_toggle_turbo_settings,
    NENOORE_OT_pick_vertex_color,
    NENOORE_OT_apply_picked_color,
    NENOORE_OT_copy_material,
    NENOORE_OT_copy_material_name,
    NENOORE_OT_apply_material,
    NENOORE_OT_add_portal_vertex,
    NENOORE_OT_reset_portal,
    NENOORE_OT_copy_single_coord,
    NENOORE_OT_copy_all_coords,
    NENOORE_OT_get_ymap_coords,
    NENOORE_OT_copy_ymap_position,
    NENOORE_OT_copy_ymap_rotation,
    NENOORE_OT_copy_ymap_xml,
    NENOORE_PT_prepare,
    NENOORE_PT_turbo,
    NENOORE_PT_material,
    NENOORE_PT_vertex_color,
    NENOORE_PT_portal,
    NENOORE_PT_ymap,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.nenoore_settings = PointerProperty(type=NENOORE_Settings)
    bpy.types.Scene.nenoore_portal_coords = CollectionProperty(type=NENOORE_PortalCoord)
    bpy.types.Scene.nenoore_ymap_props = PointerProperty(type=NENOORE_YmapProps)

def unregister():
    del bpy.types.Scene.nenoore_ymap_props
    del bpy.types.Scene.nenoore_portal_coords
    del bpy.types.Scene.nenoore_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
