# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2017 Yorik van Havre <yorik@uncreated.net>              *
# *   Copyright (c) 2022 Howetuft <howetuft-at-gmail>                       *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

"""POV-Ray renderer plugin for FreeCAD Render workbench."""

# Suggested documentation link:
# https://www.povray.org/documentation/3.7.0/r3_0.html#r3_1

# NOTE:
# Please note that POV-Ray coordinate system appears to be different from
# FreeCAD's one (z and y permuted)
# See here: https://www.povray.org/documentation/3.7.0/t2_2.html#t2_2_1_1

import os
import re
from textwrap import dedent, indent

import FreeCAD as App

TEMPLATE_FILTER = "Povray templates (povray_*.pov)"

# ===========================================================================
#                             Write functions
# ===========================================================================


def write_mesh(name, mesh, material):
    """Compute a string in renderer SDL to represent a FreeCAD mesh."""
    # POV-Ray has a lot of reserved keywords, so we suffix name with a '_' to
    # avoid any collision
    name = name + "_"

    # Material values

    # Material values
    materialvalues = material.get_material_values(
        name, _write_texture, _write_value, _write_texref
    )

    vrts = [f"<{v.x},{v.z},{v.y}>" for v in mesh.Topology[0]]
    inds = [f"<{i[0]},{i[1]},{i[2]}>" for i in mesh.Topology[1]]

    vertices = "\n        ".join(vrts)
    len_vertices = len(vrts)
    indices = "\n        ".join(inds)
    len_indices = len(inds)

    material = _write_material(name, materialvalues)

    snippet = f"""
// Generated by FreeCAD (http://www.freecadweb.org/)
// Declares object '{name}'
#declare {name} = mesh2 {{
    vertex_vectors {{
        {len_vertices},
        {vertices}
    }}
    face_indices {{
        {len_indices},
        {indices}
    }}
}}  // {name}

// Instance to render {name}
object {{
    {name}
    {material}
}}  // {name}
"""

    return snippet


def write_camera(name, pos, updir, target, fov):
    """Compute a string in renderer SDL to represent a camera."""
    # POV-Ray has a lot of reserved keywords, so we suffix name with a '_' to
    # avoid any collision
    name = name + "_"

    snippet = f"""
// Generated by FreeCAD (http://www.freecadweb.org/)
// Declares camera '{name}'
#declare cam_location = <{pos.Base.x},{pos.Base.z},{pos.Base.y}>;
#declare cam_look_at  = <{target.x},{target.z},{target.y}>;
#declare cam_sky      = <{updir.x},{updir.z},{updir.y}>;
#declare cam_angle    = {fov};
camera {{
    perspective
    location  cam_location
    look_at   cam_look_at
    sky       cam_sky
    angle     cam_angle
    right     x*800/600
}}
"""

    return snippet


def write_pointlight(name, pos, color, power):
    """Compute a string in renderer SDL to represent a point light."""
    # Note: power is of no use for POV-Ray, as light intensity is determined
    # by RGB (see POV-Ray documentation), therefore it is ignored.

    # POV-Ray has a lot of reserved keywords, so we suffix name with a '_' to
    # avoid any collision
    name = name + "_"

    snippet = f"""
// Generated by FreeCAD (http://www.freecadweb.org/)
// Declares point light '{name}'
light_source {{
    <{pos.x},{pos.z},{pos.y}>
    color rgb<{color[0]},{color[1]},{color[2]}>
}}
"""

    return snippet


def write_arealight(name, pos, size_u, size_v, color, power, transparent):
    """Compute a string in renderer SDL to represent an area light."""
    # POV-Ray has a lot of reserved keywords, so we suffix name with a '_' to
    # avoid any collision
    name = name + "_"

    # Dimensions of the point sources array
    # (area light is treated as point sources array, see POV-Ray documentation)
    size_1 = 20
    size_2 = 20

    # Prepare area light axes
    rot = pos.Rotation
    axis1 = rot.multVec(App.Vector(size_u, 0.0, 0.0))
    axis2 = rot.multVec(App.Vector(0.0, size_v, 0.0))

    # Prepare shape points for 'look_like'
    points = [
        (+axis1 + axis2) / 2,
        (+axis1 - axis2) / 2,
        (-axis1 - axis2) / 2,
        (-axis1 + axis2) / 2,
        (+axis1 + axis2) / 2,
    ]
    points = [f"<{p.x},{p.z},{p.y}>" for p in points]
    points = ", ".join(points)

    snippet = f"""
// Generated by FreeCAD (http://www.freecadweb.org/)
// Declares area light {name}
#declare {name}_shape = polygon {{
    5, {points}
    texture {{ pigment{{ color rgb <{color[0]},{color[1]},{color[2]}>}}
              finish {{ ambient 1 }}
            }} // end of texture
}}
light_source {{
    <{pos.Base.x},{pos.Base.z},{pos.Base.y}>
    color rgb <{color[0]},{color[1]},{color[2]}>
    area_light <{axis1.x},{axis1.z},{axis1.y}>,
               <{axis2.x},{axis2.z},{axis2.y}>,
               {size_1}, {size_2}
    adaptive 1
    looks_like {{ {name}_shape }}
    jitter
}}
"""
    return snippet


def write_sunskylight(name, direction, distance, turbidity, albedo):
    """Compute a string in renderer SDL to represent a sunsky light.

    Since POV-Ray does not provide a built-in Hosek-Wilkie feature, sunsky is
    modeled by a white parallel light, with a simple gradient skysphere.
    Please note it is a very approximate and limited model (works better for
    sun high in the sky...)
    """
    # POV-Ray has a lot of reserved keywords, so we suffix name with a '_' to
    # avoid any collision
    name = name + "_"

    location = direction.normalize()
    location.Length = distance

    snippet = f"""
// Generated by FreeCAD (http://www.freecadweb.org/)
// Declares sunsky light {name}
// sky ------------------------------------
sky_sphere{{
    pigment{{ gradient y
       color_map{{
           [0.0 color rgb<1,1,1> ]
           [0.8 color rgb<0.18,0.28,0.75>]
           [1.0 color rgb<0.75,0.75,0.75>]}}
           //[1.0 color rgb<0.15,0.28,0.75>]}}
           scale 2
           translate -1
    }} // end pigment
}} // end sky_sphere
// sun -----------------------------------
global_settings {{ ambient_light rgb<1, 1, 1> }}
light_source {{
    <{location.x},{location.z},{location.y}>
    color rgb <1,1,1>
    parallel
    point_at <0,0,0>
    adaptive 1
}}
"""

    return snippet


def write_imagelight(name, image):
    """Compute a string in renderer SDL to represent an image-based light."""
    # POV-Ray has a lot of reserved keywords, so we suffix name with a '_' to
    # avoid any collision
    name = name + "_"

    snippet = f"""
// Generated by FreeCAD (http://www.freecadweb.org/)
// Declares image-based light {name}
// hdr environment -----------------------
sky_sphere{{
    matrix < -1, 0, 0,
              0, 1, 0,
              0, 0, 1,
              0, 0, 0 >
    pigment{{
        image_map{{ hdr "{file}"
                   gamma 1
                   map_type 1 interpolate 2}}
    }} // end pigment
}} // end sphere with hdr image
"""

    return snippet


# ===========================================================================
#                              Material implementation
# ===========================================================================


def _write_material(name, material):
    """Compute a string in the renderer SDL, to represent a material.

    This function should never fail: if the material is not recognized,
    a fallback material is provided.
    """
    try:
        snippet_mat = MATERIALS[material.shadertype](name, material)
    except KeyError:
        msg = (
            "'{}' - Material '{}' unknown by renderer, using fallback "
            "material\n"
        )
        App.Console.PrintWarning(msg.format(name, material.shadertype))
        snippet_mat = _write_material_fallback(name, material.default_color)
    return snippet_mat


def _write_material_passthrough(name, material):
    """Compute a string in the renderer SDL for a passthrough material."""
    assert material.passthrough.renderer == "Povray"
    snippet = indent(material.passthrough.string, "    ")
    return snippet.format(n=name, c=material.default_color)


def _write_material_glass(name, material):
    """Compute a string in the renderer SDL for a glass material."""
    snippet = """
    texture {{
        pigment {{color rgbf <{c.r}, {c.g}, {c.b}, 0.7>}}
        finish {{
            specular 1
            roughness 0.001
            ambient 0
            diffuse 0
            reflection 0.1
            }}
        }}
    interior {{
        ior {i}
        caustics 1
        }}"""
    return snippet.format(n=name, c=material.glass.color, i=material.glass.ior)


def _write_material_disney(name, material):
    """Compute a string in the renderer SDL for a Disney material.

    Caveat: this is a very rough implementation, as the Disney shader does not
    exist at all in Pov-Ray.
    """
    snippet = """
    texture {{
        pigment {{ color rgb <{c.r}, {c.g}, {c.b}> }}
        finish {{
            diffuse albedo 0.8
            specular {sp}
            roughness {r}
            conserve_energy
            reflection {{
                {sp}
                metallic
                }}
            {subsurface}
            irid {{ {ccg} }}
            }}

    }}"""
    # If disney.subsurface is 0, we just omit the subsurface statement,
    # as it is very slow to render
    subsurface = (
        f"subsurface {{ translucency {material.disney.subsurface} }}"
        if material.disney.subsurface > 0
        else ""
    )
    return snippet.format(
        n=name,
        c=material.disney.basecolor,
        subsurface=subsurface,
        m=material.disney.metallic,
        sp=material.disney.specular,
        spt=material.disney.speculartint,
        r=material.disney.roughness,
        a=material.disney.anisotropic,
        sh=material.disney.sheen,
        sht=material.disney.sheentint,
        cc=material.disney.clearcoat,
        ccg=material.disney.clearcoatgloss,
    )


def _write_material_diffuse(name, matval):
    """Compute a string in the renderer SDL for a Diffuse material."""
    snippet = f"""    texture {{
        pigment {{ {matval["color"]} }}
        finish {{
            diffuse albedo 1
            }}
        }}"""
    return snippet


def _write_material_mixed(name, material):
    """Compute a string in the renderer SDL for a Mixed material."""
    snippet = """
    texture {{
        pigment {{ rgbf <{k.r}, {k.g}, {k.b}, 0.7> }}
        finish {{
            phong 1
            roughness 0.001
            ambient 0
            diffuse 0
            reflection 0.1
            }}
    }}
    interior {{ior {i} caustics 1}}
    texture {{
        pigment {{ rgbt <{c.r}, {c.g}, {c.b}, {t}> }}
        finish {{ diffuse 1 }}
    }}"""
    return snippet.format(
        n=name,
        t=material.mixed.transparency,
        c=material.mixed.diffuse.color,
        k=material.mixed.glass.color,
        i=material.mixed.glass.ior,
    )


def _write_material_carpaint(name, material):
    """Compute a string in the renderer SDL for a carpaint material."""
    snippet = """
    texture {{
        pigment {{ rgb <{c.r}, {c.g}, {c.b}> }}
        finish {{
            diffuse albedo 0.7
            phong albedo 0
            specular albedo 0.6
            roughness 0.001
            reflection {{ 0.05 }}
            irid {{ 0.5 }}
            conserve_energy
        }}
    }}"""
    return snippet.format(n=name, c=material.carpaint.basecolor)


def _write_material_fallback(name, material):
    """Compute a string in the renderer SDL for a fallback material.

    Fallback material is a simple Diffuse material.
    """
    try:
        red = float(material.default_color.r)
        grn = float(material.default_color.g)
        blu = float(material.default_color.b)
        assert (0 <= red <= 1) and (0 <= grn <= 1) and (0 <= blu <= 1)
    except (AttributeError, ValueError, TypeError, AssertionError):
        red, grn, blu = 1, 1, 1
    snippet = """    texture {{
        pigment {{rgb <{r}, {g}, {b}>}}
        finish {{
            diffuse albedo 1
            }}
        }}"""
    return snippet.format(n=name, r=red, g=grn, b=blu)


MATERIALS = {
    "Passthrough": _write_material_passthrough,
    "Glass": _write_material_glass,
    "Disney": _write_material_disney,
    "Diffuse": _write_material_diffuse,
    "Mixed": _write_material_mixed,
    "Carpaint": _write_material_carpaint,
}


# ===========================================================================
#                                Textures
# ===========================================================================

# TODO
import mimetypes

mimetypes.init()

IMAGE_MIMETYPES = {
    "image/bmp": "bmp",
    "image/aces": "exr",
    "image/gif": "gif",
    "image/vnd.radiance": "hdr",
    "image/jpeg": "jpeg",
    "image/x-portable-graymap": "pgm",
    "image/png": "png",
    "image/x-portable-pixmap": "ppm",
    "image/x-tga": "tga",
    "image/tiff": "tiff",
}  # Povray claims to support also iff and sys, but I don't know those formats


def _imagetype(path):
    mimetype = mimetypes.guess_type(path)
    return IMAGE_MIMETYPES.get(mimetype[0], "")


def _write_texture(**kwargs):
    """Compute a string in renderer SDL to describe a texture.

    The texture is computed from a property of a shader (as the texture is
    always integrated into a shader). Property's data are expected as
    arguments.

    Args:
        objname -- Object name for which the texture is computed
        propvalue -- Value of the shader property

    Returns:
        the name of the texture
        the SDL string of the texture
    """
    # Retrieve parameters
    objname = kwargs["objname"]
    propvalue = kwargs["propvalue"]

    # Compute texture name
    texname = f"{objname}_{propvalue.name}_{propvalue.subname}"

    # In Povray, no separate texture declaration...
    return texname, ""


VALSNIPPETS = {
    "RGB": "rgb <{val.r}, {val.g}, {val.b}>",
    "float": "{val}",
    "node": "",
    "RGBA": "{val.r} {val.g} {val.b} {val.a}",
    "texonly": "{val}",
    "str": "{val}",
}


def _write_value(**kwargs):
    """Compute a string in renderer SDL from a shader property value.

    Args:
        proptype -- Shader property's type
        propvalue -- Shader property's value

    The result depends on the type of the value...
    """
    # Retrieve parameters
    proptype = kwargs["proptype"]
    propvalue = kwargs["propvalue"]

    # Snippets for values
    snippet = VALSNIPPETS[proptype]
    value = snippet.format(val=propvalue)

    return value


def _write_texref(**kwargs):
    """Compute a string in SDL for a reference to a texture in a shader."""
    # Retrieve parameters
    propname = kwargs["propname"]
    proptype = kwargs["proptype"]
    propvalue = kwargs["propvalue"]

    # Compute gamma
    gamma = "srgb" if proptype == "RGB" else 1.0

    # TODO
    if propname in ["bump", "normal", "displacement"]:
        return ""

    imagefile = propvalue.file

    texture = f"""image_map {{ {_imagetype(imagefile)} "{imagefile}" gamma {gamma} }}"""

    return texture


# ===========================================================================
#                              Render function
# ===========================================================================


def render(project, prefix, external, output, width, height):
    """Generate renderer command.

    Args:
        project -- The project to render
        prefix -- A prefix string for call (will be inserted before path to
            renderer)
        external -- A boolean indicating whether to call UI (true) or console
            (false) version of renderder
        width -- Rendered image width, in pixels
        height -- Rendered image height, in pixels

    Returns:
        The command to run renderer (string)
        A path to output image file (string)
    """
    params = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Render")

    prefix = params.GetString("Prefix", "")
    if prefix:
        prefix += " "

    rpath = params.GetString("PovRayPath", "")
    if not rpath:
        App.Console.PrintError(
            "Unable to locate renderer executable. "
            "Please set the correct path in "
            "Edit -> Preferences -> Render\n"
        )
        return None, None

    args = params.GetString("PovRayParameters", "")
    if args:
        args += " "
    if "+W" in args:
        args = re.sub(r"\+W[0-9]+", f"+W{width}", args)
    else:
        args = args + f"+W{width} "
    if "+H" in args:
        args = re.sub(r"\+H[0-9]+", f"+H{height}", args)
    else:
        args = args + f"+H{height} "
    if output:
        args = args + f"+O{output} "

    filepath = f'"{project.PageResult}"'

    cmd = prefix + rpath + " " + args + " " + filepath

    output = (
        output if output else os.path.splitext(project.PageResult)[0] + ".png"
    )

    return cmd, output
