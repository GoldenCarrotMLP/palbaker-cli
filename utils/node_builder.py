import bpy
import os

PARAMETER_MAPPING = {
    "base_color": ["Base Color Texture (RGB)", "Base Texture", "BaseColor", "Diffuse", "Albedo"],
    "normal": ["Normal Map", "NormalTexture", "Normal"],
    "mrao": ["MetallicRoughnessOcclusionSpecularTexture", "ParameterMap", "MaskMap", "MRAO"],
    "subsurface": ["Subsurface Texture", "Subsurface"]
}

def get_mapped_texture(params, role):
    keywords = [k.lower() for k in PARAMETER_MAPPING.get(role, [])]
    for param_name, tex_name in params.items():
        if param_name.lower() in keywords:
            return tex_name
    for param_name, tex_name in params.items():
        if any(kw in param_name.lower() for kw in keywords):
            return tex_name
    return None

def create_texture_node(nodes, working_dir, texture_name, loc_x, loc_y, non_color=False):
    tex_node = nodes.new("ShaderNodeTexImage")
    tex_node.location = (loc_x, loc_y)
    
    if texture_name:
        img_path = os.path.join(working_dir, f"{texture_name}.png")
        if os.path.exists(img_path):
            img = bpy.data.images.get(f"{texture_name}.png")
            if not img:
                img = bpy.data.images.load(img_path)
            if non_color:
                img.colorspace_settings.name = 'Non-Color'
            tex_node.image = img
            
    return tex_node

def build_eye_template(mat, params, working_dir):
    mat.use_nodes = True
    mat.blend_method = 'HASHED'
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output_node = nodes.new("ShaderNodeOutputMaterial")
    output_node.location = (300, 100)
    
    bsdf_node = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf_node.location = (-100, 100)
    links.new(bsdf_node.outputs["BSDF"], output_node.inputs["Surface"])

    tex_base_name = get_mapped_texture(params, "base_color")
    tex_node = create_texture_node(nodes, working_dir, tex_base_name, -500, 100)
    
    links.new(tex_node.outputs["Color"], bsdf_node.inputs["Base Color"])
    links.new(tex_node.outputs["Alpha"], bsdf_node.inputs["Alpha"])

def build_body_template(mat, params, working_dir):
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output_node = nodes.new("ShaderNodeOutputMaterial")
    output_node.location = (300, 100)
    
    bsdf_node = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf_node.location = (-100, 100)
    links.new(bsdf_node.outputs["BSDF"], output_node.inputs["Surface"])

    mix_node = nodes.new("ShaderNodeMix")
    mix_node.data_type = 'RGBA'
    mix_node.blend_type = 'MULTIPLY'
    mix_node.inputs["Factor"].default_value = 1.0
    mix_node.location = (-400, 200)
    links.new(mix_node.outputs["Result"], bsdf_node.inputs["Base Color"])

    sep_color = nodes.new("ShaderNodeSeparateColor")
    sep_color.mode = 'RGB'
    sep_color.location = (-800, 0)
    links.new(sep_color.outputs["Red"], bsdf_node.inputs["Metallic"])
    links.new(sep_color.outputs["Green"], bsdf_node.inputs["Roughness"])
    links.new(sep_color.outputs["Blue"], mix_node.inputs["B"])

    norm_map = nodes.new("ShaderNodeNormalMap")
    norm_map.location = (-400, -300)
    if hasattr(norm_map, "convention"):
        norm_map.convention = 'DIRECTX'
    links.new(norm_map.outputs["Normal"], bsdf_node.inputs["Normal"])

    tex_base_name = get_mapped_texture(params, "base_color")
    base_tex = create_texture_node(nodes, working_dir, tex_base_name, -800, 300)
    links.new(base_tex.outputs["Color"], mix_node.inputs["A"])

    tex_mrao_name = get_mapped_texture(params, "mrao")
    if tex_mrao_name:
        mrao_tex = create_texture_node(nodes, working_dir, tex_mrao_name, -1200, 0, non_color=True)
        links.new(mrao_tex.outputs["Color"], sep_color.inputs["Color"])
    else:
        # Fallback to Color Pickers
        combine_node = nodes.new("ShaderNodeCombineColor")
        combine_node.mode = 'RGB'
        combine_node.location = (-1200, 0)
        
        color_r = nodes.new("ShaderNodeRGB")
        color_r.location = (-1500, 100)
        color_r.outputs[0].default_value = (0.0, 0.0, 0.0, 1.0)
        
        color_g = nodes.new("ShaderNodeRGB")
        color_g.location = (-1500, -100)
        color_g.outputs[0].default_value = (0.5, 0.5, 0.5, 1.0)
        
        color_b = nodes.new("ShaderNodeRGB")
        color_b.location = (-1500, -300)
        color_b.outputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
        
        links.new(color_r.outputs[0], combine_node.inputs["Red"])
        links.new(color_g.outputs[0], combine_node.inputs["Green"])
        links.new(color_b.outputs[0], combine_node.inputs["Blue"])
        links.new(combine_node.outputs["Color"], sep_color.inputs["Color"])

    tex_norm_name = get_mapped_texture(params, "normal")
    norm_tex = create_texture_node(nodes, working_dir, tex_norm_name, -800, -300, non_color=True)
    links.new(norm_tex.outputs["Color"], norm_map.inputs["Color"])

    tex_sss_name = get_mapped_texture(params, "subsurface")
    sss_tex = create_texture_node(nodes, working_dir, tex_sss_name, -400, -600)
    links.new(sss_tex.outputs["Color"], bsdf_node.inputs["Subsurface Radius"])

def build_material(mat, parent_class, params, working_dir):
    parent_lower = parent_class.lower()
    if "eye" in parent_lower or "mouth" in parent_lower:
        build_eye_template(mat, params, working_dir)
    else:
        build_body_template(mat, params, working_dir)