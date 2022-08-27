# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2020 Howetuft <howetuft@gmail.com>                      *
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

"""This module implements material management mechanisms for rendering."""

# ===========================================================================
#                           Imports
# ===========================================================================


import collections
import types
import functools
from collections import namedtuple

import FreeCAD as App

from Render.utils import (
    RGBA,
    str2rgb,
    parse_csv_str,
    debug as ru_debug,
    getproxyattr,
    translate,
)
from Render.texture import str2imageid


# ===========================================================================
#                                   Export
# ===========================================================================

Param = collections.namedtuple("Param", "name type default desc")

# IMPORTANT: Please note that, by convention, the first parameter of each
# material will be used as default color in fallback mechanisms.
# Please be careful to preserve a color-typed field as first parameter of each
# material, if you modify an existing material or you add a new one...
STD_MATERIALS_PARAMETERS = {
    "Glass": [
        Param(
            "Color", "RGB", (1, 1, 1), translate("Render", "Transmitted color")
        ),
        Param("IOR", "float", 1.5, translate("Render", "Index of refraction")),
        Param(
            "Bump",
            "texonly",
            "",
            translate("Render", "Bump"),
        ),
        Param(
            "Normal",
            "texonly",
            "",
            translate("Render", "Normal"),
        ),
    ],
    "Disney": [
        Param(
            "BaseColor",
            "RGB",
            (0.8, 0.8, 0.8),
            translate("Render", "Base color"),
        ),
        Param(
            "Subsurface",
            "float",
            0.0,
            translate("Render", "Subsurface coefficient"),
        ),
        Param(
            "Metallic",
            "float",
            0.0,
            translate("Render", "Metallic coefficient"),
        ),
        Param(
            "Specular",
            "float",
            0.0,
            translate("Render", "Specular coefficient"),
        ),
        Param(
            "SpecularTint",
            "float",
            0.0,
            translate("Render", "Specular tint coefficient"),
        ),
        Param(
            "Roughness",
            "float",
            0.0,
            translate("Render", "Roughness coefficient"),
        ),
        Param(
            "Anisotropic",
            "float",
            0.0,
            translate("Render", "Anisotropic coefficient"),
        ),
        Param("Sheen", "float", 0.0, translate("Render", "Sheen coefficient")),
        Param(
            "SheenTint",
            "float",
            0.0,
            translate("Render", "Sheen tint coefficient"),
        ),
        Param(
            "ClearCoat",
            "float",
            0.0,
            translate("Render", "Clear coat coefficient"),
        ),
        Param(
            "ClearCoatGloss",
            "float",
            0.0,
            translate("Render", "Clear coat gloss coefficient"),
        ),
        Param(
            "Bump",
            "texonly",
            "",
            translate("Render", "Bump"),
        ),
        Param(
            "Normal",
            "texonly",
            "",
            translate("Render", "Normal"),
        ),
        Param(
            "Displacement",
            "texonly",
            "",
            translate("Render", "Displacement"),
        ),
    ],
    "Diffuse": [
        Param(
            "Color",
            "RGB",
            (0.8, 0.8, 0.8),
            translate("Render", "Diffuse color"),
        ),
        Param(
            "Bump",
            "texonly",
            "",
            translate("Render", "Bump"),
        ),
        Param(
            "Normal",
            "texonly",
            "",
            translate("Render", "Normal"),
        ),
    ],
    # NB: Above 'Mixed' material could be extended with reflectivity in the
    # future, with the addition of a Glossy material. See for instance:
    # https://download.blender.org/documentation/bc2012/FGastaldo_PhysicallyCorrectshading.pdf
    "Mixed": [
        Param(
            "Diffuse.Color",
            "RGB",
            (0.8, 0.8, 0.8),
            translate("Render", "Diffuse color"),
        ),
        Param(
            "Glass.Color",
            "RGB",
            (1, 1, 1),
            translate("Render", "Transmitted color"),
        ),
        Param(
            "Glass.IOR",
            "float",
            1.5,
            translate("Render", "Index of refraction"),
        ),
        Param(
            "Transparency",
            "float",
            0.5,
            translate(
                "Render",
                "Mix ratio between Glass and Diffuse "
                "(should stay in [0,1], other values "
                "may lead to undefined behaviour)",
            ),
        ),
        Param(
            "Bump",
            "texonly",
            "",
            translate("Render", "Bump"),
        ),
        Param(
            "Normal",
            "texonly",
            "",
            translate("Render", "Normal"),
        ),
    ],
    "Carpaint": [
        Param(
            "BaseColor",
            "RGB",
            (0.8, 0.2, 0.2),
            translate("Render", "Base color"),
        ),
        Param(
            "Bump",
            "texonly",
            "",
            translate("Render", "Bump"),
        ),
        Param(
            "Normal",
            "texonly",
            "",
            translate("Render", "Normal"),
        ),
    ],
}


STD_MATERIALS = sorted(list(STD_MATERIALS_PARAMETERS.keys()))


RendererTexture = namedtuple(
    "RendererTexture",
    [
        "name",
        "subname",
        "file",
        "rotation",
        "scale",
        "translation_u",
        "translation_v",
        "is_texture",
    ],
)
RendererTexture.__new__.__defaults__ = (None,) * 1  # Python 3.6 style


def _castrgb(*args):
    """Cast extended RGB field value to RGB object or RendererTexture object.

    This function can handle "object color" special case:
    'value' is treated as a semicolon separated value.
    if 'value' contains "Object", 'objcol' is returned

    Args:
        value -- the value to parse and cast
        objcol -- the object color

    Returns:
        a RGB object containing the targeted color **or** a RendererTexture
        object if appliable.
    """
    value = str(args[0])
    objcol = args[1]

    parsed = parse_csv_str(value)

    if "Object" in parsed:
        return objcol

    if "Texture" in parsed:
        # Build RendererTexture
        imageid = str2imageid(parsed[1])
        texobject = App.ActiveDocument.getObject(
            imageid.texture
        )  # Texture object
        file = texobject.getPropertyByName(imageid.image)
        res = RendererTexture(
            texobject.Label,
            imageid.image,
            file,
            texobject.Rotation.getValueAs("deg"),
            float(texobject.Scale),
            texobject.TranslationU.getValueAs("m"),
            texobject.TranslationV.getValueAs("m"),
        )
        return res

    # Default (and fallback) case, return color
    return str2rgb(parsed[0])


def _castfloat(*args):
    """Cast extended float field value to float or RendererTexture object.

    Args:
        value -- the value to parse and cast

    Returns:
        a float containing the targeted value **or** a RendererTexture object
        if appliable.
    """
    value = str(args[0])

    parsed = parse_csv_str(value)

    if "Texture" in parsed:
        # Build RendererTexture
        imageid = str2imageid(parsed[1])
        texobject = App.ActiveDocument.getObject(
            imageid.texture
        )  # Texture object
        file = texobject.getPropertyByName(imageid.image)
        res = RendererTexture(
            texobject.Label,
            imageid.image,
            file,
            texobject.Rotation.getValueAs("deg"),
            float(texobject.Scale),
            texobject.TranslationU.getValueAs("m"),
            texobject.TranslationV.getValueAs("m"),
        )
        return res

    # Default (and fallback) case, return float
    value = parsed[0]
    return float(value) if value else 0.0


def _caststr(*args):
    """Cast to string value.

    Args:
        value -- the value to cast

    Returns:
        The cast string value.
    """
    value = str(args[0])
    return value


def _casttexonly(*args):
    """Cast to texonly value.

    Args:
        value -- the value to cast

    Returns:
        The cast string value.
    """
    value = args[0]

    parsed = parse_csv_str(str(value))

    if "Texture" in parsed:
        # Build RendererTexture
        imageid = str2imageid(parsed[1])
        texobject = App.ActiveDocument.getObject(
            imageid.texture
        )  # Texture object
        file = texobject.getPropertyByName(imageid.image)
        res = RendererTexture(
            texobject.Label,
            imageid.image,
            file,
            texobject.Rotation.getValueAs("deg"),
            float(texobject.Scale),
            texobject.TranslationU.getValueAs("m"),
            texobject.TranslationV.getValueAs("m"),
        )
        return res

    # Default (and fallback), return empty
    return None


CAST_FUNCTIONS = {
    "float": _castfloat,
    "RGB": _castrgb,
    "string": _caststr,
    "texonly": _casttexonly,
}


def get_rendering_material(material, renderer, default_color):
    """Get rendering material from FreeCAD material.

    This function implements rendering material logic.
    It extracts a data class of rendering parameters from a FreeCAD material
    card.
    The workflow is the following:
    - If the material card contains a renderer-specific Passthrough field, the
      dictionary is built with those parameters
    - Otherwise, if the material card contains standard materials parameters,
      the dictionary is built with those parameters
    - Otherwise, if the material card contains a valid 'father' field, the
      above process is applied to the father card
    - Otherwise, if the material card contains a Graphic section
      (diffusecolor), a Diffuse material is built and the dictionary contains
      the related parameters . This is a backward compatibility fallback
    - Otherwise, a Diffuse material made with default_color is returned

    Parameters:
    material -- a FreeCAD material
    renderer -- the targeted renderer (string, case sensitive)
    default_color -- a RGBA color, to be used as a fallback

    Returns:
    A data object providing some systematic and specific properties for the
    targeted shader.

    Systematic properties:
    shadertype -- the type of shader for rendering. Can be "Passthrough",
    "Disney", "Glass", "Diffuse"

    Specific properties, depending on 'shadertype':
    "Passthrough": string, renderer
    "Disney": basecolor, subsurface, metallic, specular, speculartint,
    roughness, anisotropic, sheen, sheentint, clearcoat, clearcoatgloss
    "Glass": ior, color
    "Diffuse": color

    Please note the function is not responsible for syntactic compliance of the
    parameters in the material card (i.e. the parameters are not parsed, just
    collected from the material card)
    """
    # Check valid material
    if not is_valid_material(material):
        ru_debug("Material", "<None>", "Fallback to default material")
        return _build_fallback(default_color)

    # Initialize
    mat = dict(material.Material)
    renderer = str(renderer)
    name = mat.get("Name", "<Unnamed Material>")
    debug = functools.partial(ru_debug, "Material", name)

    debug("Starting material computation")

    # Try renderer Passthrough
    common_keys = passthrough_keys(renderer) & mat.keys()
    if common_keys:
        lines = tuple(mat[k] for k in sorted(common_keys))
        debug("Found valid Passthrough - returning")
        return _build_passthrough(lines, renderer, default_color)

    # Try standard materials
    shadertype = mat.get("Render.Type", None)
    if shadertype:
        try:
            params = STD_MATERIALS_PARAMETERS[shadertype]
        except KeyError:
            debug(f"Unknown material type '{shadertype}'")
        else:
            values = tuple(
                (
                    p.name,  # Parameter name
                    mat.get(f"Render.{shadertype}.{p.name}", None),  # Par val
                    p.default,  # Parameter default value
                    p.type,  # Parameter type
                    default_color,  # Object color
                )
                for p in params
            )
            return _build_standard(shadertype, values)

    # Climb up to Father
    debug("No valid material definition - trying father material")
    try:
        father_name = mat["Father"]
        assert father_name
        materials = (
            o for o in App.ActiveDocument.Objects if is_valid_material(o)
        )
        father = next(
            m for m in materials if m.Material.get("Name", "") == father_name
        )
    except (KeyError, AssertionError):
        # No father
        debug("No valid father")
    except StopIteration:
        # Found father, but not in document
        msg = (
            "Found father material name ('{}') but "
            "did not find this material in active document"
        )
        debug(msg.format(father_name))
    else:
        # Found usable father
        debug(f"Retrieve father material '{father_name}'")
        return get_rendering_material(father, renderer, default_color)

    # Try with Coin-like parameters (backward compatibility)
    try:
        diffusecolor = str2rgb(mat["DiffuseColor"])
    except (KeyError, TypeError):
        pass
    else:
        debug("Fallback to Coin-like parameters")
        color = RGBA(
            diffusecolor.r,
            diffusecolor.g,
            diffusecolor.b,
            float(mat.get("Transparency", "0")) / 100,
        )
        return _build_fallback(color)

    # Fallback with default_color
    debug("Fallback to default color")
    return _build_fallback(default_color)


@functools.lru_cache(maxsize=128)
def passthrough_keys(renderer):
    """Compute material card keys for passthrough rendering material."""
    return {f"Render.{renderer}.{i:04}" for i in range(1, 9999)}


def is_multimat(obj):
    """Check if a material is a multimaterial."""
    try:
        is_app_feature = obj.isDerivedFrom("App::FeaturePython")
    except AttributeError:
        return False

    is_type_multimat = getproxyattr(obj, "Type", None) == "MultiMaterial"

    return obj is not None and is_app_feature and is_type_multimat


def generate_param_doc():
    """Generate Markdown documentation from material rendering parameters."""
    header_fmt = [
        "#### **{m}** Material",
        "",
        "`Render.Type={m}`",
        "",
        "Parameter | Type | Default value | Description",
        "--------- | ---- | ------------- | -----------",
    ]

    line_fmt = "`Render.{m}.{p.name}` | {p.type} | {p.default} | {p.desc}"
    footer_fmt = [""]
    lines = []
    for mat in STD_MATERIALS:
        lines += [h.format(m=mat) for h in header_fmt]
        lines += [
            line_fmt.format(m=mat, p=param)
            for param in STD_MATERIALS_PARAMETERS[mat]
        ]
        lines += footer_fmt

    return "\n".join(lines)


def is_valid_material(obj):
    """Assert that an object is a valid Material."""
    try:
        is_materialobject = obj.isDerivedFrom("App::MaterialObjectPython")
    except AttributeError:
        return False

    return (
        obj is not None
        and is_materialobject
        and hasattr(obj, "Material")
        and isinstance(obj.Material, dict)
    )


# ===========================================================================
#                             Objects for renderers
# ===========================================================================


class RenderMaterial:
    """An object to represent a material for renderers plugins.

    Such an object is passed to renderers plugins by the renderer handler,
    to provide them data about a material.
    """

    def __init__(self, shadertype):
        """Initialize object."""
        shadertype = str(shadertype)
        self.shadertype = shadertype
        setattr(self, shadertype.lower(), types.SimpleNamespace())
        self.default_color = RGBA(0.8, 0.8, 0.8, 1.0)
        self._partypes = {}  # Record parameter types

    def __repr__(self):
        """Represent object."""
        items = (f"{k}={v!r}" for k, v in self.__dict__.items())
        return f"{type(self).__name__}({', '.join(items)})"

    def setshaderparam(self, name, value, paramtype=None):
        """Set shader parameter.

        Args:
            name -- The parameter's name
            value -- The value to give to this parameter
            paramtype -- The parameter type, to be recorded (should be the same
                as in STD_MATERIALS_PARAMETERS)

        If parameter does not exist, add it.
        If parameter name is a compound like 'foo.bar.baz', foo and bar are
        added as SimpleNamespaces.
        """
        # Break down parameter path
        path = [e.lower() for e in [self.shadertype] + name.split(".")]

        # Find parameter position (and create sub-namespaces if necessary)
        pos = self
        for elem in path[:-1]:  # Except last subname
            if not hasattr(pos, elem):
                setattr(pos, elem, types.SimpleNamespace())
                self._partypes[elem] = "node"
                setattr(pos, "shader", elem)
                self._partypes["shader"] = "str"
            pos = getattr(pos, elem)

        # Set parameter value
        setattr(pos, path[-1], value)

        # Record parameter type
        self._partypes[path[-1]] = paramtype

    def getmixedsubmat(self, subname, nodename="mixed"):
        """Build a RenderMaterial from a mixed submaterial."""
        res = RenderMaterial(subname)  # Resulting RenderMat to be returned
        # Copy submat into result
        node = getattr(self, nodename)
        submatsrc = getattr(node, subname)
        setattr(res, subname, submatsrc)

        # Initialize _partypes
        res._partypes = self._partypes  # pylint: disable=protected-access

        return res

    def getshaderparam(self, name):
        """Get shader parameter.

        If parameter name is a compound like 'foo.bar.baz', the method
        retrieves self.foo.bar.baz .
        If one of the path element is missing in self, an AttributeError will
        be raised.
        """
        path = [e.lower() for e in [self.shadertype] + name.split(".")]
        res = self
        for elem in path:
            res = getattr(res, elem)
        return res

    @property
    def shadername(self):
        """Get shader name."""
        return self.shadertype.lower()

    @property
    def shader(self):
        """Get shader attribute, whatever underlying attribute it is."""
        return getattr(self, self.shadername)

    @property
    def shaderproperties(self):
        """Get shader's properties, as a dictionary."""
        return self.shader.__dict__

    def get_param_type(self, param_name):
        """Get parameter type."""
        return self._partypes[param_name]

    def get_material_values(
        self, objname, write_texture_fun, write_value_fun, write_texref_fun
    ):
        """Provide a MaterialValues object.

        This method is intended to be called from inside the _write_mesh
        function of a renderer plugin, for texture management.

        The MaterialValues is build from this RenderMaterial, the name of the
        object to render, and the export functions for textures and values from
        the plugin.
        """
        materialvalues = MaterialValues(
            objname, self, write_texture_fun, write_value_fun, write_texref_fun
        )
        return materialvalues


class MaterialValues:
    """Material values wrapper.

    This wrapper customizes a material for a specific object and a specific
    renderer. Objects of this class are generated only by RenderMaterial. The
    renderer must call RenderMaterial.get_material_values to get such an
    object.

    This wrapper implements 2 main methods:
    - a `textures` method which provides a list of the embedded textures
      expanded in SDL.
    - a `__setitem__` which provides the computed value for a parameter:
      either a sheer value or a reference to a texture, depending on the actual
      underlying value.
    """

    def __init__(
        self,
        objname,
        material,
        write_texture_fun,
        write_value_fun,
        write_texref_fun,
    ):
        """Initialize material values.

        Args:
            objname -- Name of the object for which the values are computed
            material -- The rendering material from which we compute the values
            write_texture_fun  -- The function to call back to get a texture in
                SDL string
            write_value_fun -- The function to call back to get a value in SDL
                string
            write_texref_fun  -- The function to call back to get a texture
                reference in SDL
        """
        self.material = material
        self.shader = material.shader
        self.objname = str(objname)
        self._values = {}
        self._textures = []
        self._write_texture = write_texture_fun
        self._write_value = write_value_fun
        self._write_texref = write_texref_fun

        # Build values and textures - loop on shader properties
        for propkey, propvalue in material.shaderproperties.items():
            # None value: not handled, continue
            if propvalue is None:
                continue

            # Get property type
            proptype = material.get_param_type(propkey)

            # Is it a texture?
            if hasattr(propvalue, "is_texture"):
                # Compute texture
                texname, texture = write_texture_fun(
                    objname=objname,
                    propname=propkey,
                    proptype=proptype,
                    propvalue=propvalue,
                )
                # Add texture SDL to internal list of textures
                self._textures.append(texture)
                value = write_texref_fun(
                    texname=texname,
                    propname=propkey,
                    proptype=proptype,
                    propvalue=propvalue,
                )
            else:
                # Not a texture, treat as plain value...
                value = write_value_fun(proptype=proptype, propvalue=propvalue)

            # Store resulting value
            self._values[propkey] = value

    def textures(self):
        """Get a list of material's textures."""
        return self._textures

    def write_textures(self):
        """Get an SDL representation of all textures."""
        return "\n".join(self._textures)

    def __getitem__(self, propname):
        """Implement self[propname]."""
        return self._values[propname]

    def has_bump(self):
        """Check if material has a bump texture (boolean)."""
        return ("bump" in self._values) and (self._values["bump"] is not None)

    def has_normal(self):
        """Check if material has a normal texture (boolean)."""
        return ("normal" in self._values) and (
            self._values["normal"] is not None
        )

    def has_displacement(self):
        """Check if material has a normal texture (boolean)."""
        return ("displacement" in self._values) and (
            self._values["displacement"] is not None
        )

    @property
    def default_color(self):
        """Get material default color."""
        return self.material.default_color

    @property
    def shadertype(self):
        """Get material default color."""
        return self.material.shadertype

    def getmixedsubmat(self, submat):
        """Get mixed submaterial."""
        return MaterialValues(
            self.objname,
            self.material.getmixedsubmat(submat),
            self._write_texture,
            self._write_value,
            self._write_texref,
        )


# ===========================================================================
#                            Local helpers
# ===========================================================================


@functools.lru_cache(maxsize=128)
def _build_standard(shadertype, values):
    """Build standard material."""
    res = RenderMaterial(shadertype)

    for nam, val, dft, typ, objcol in values:
        cast_function = CAST_FUNCTIONS[typ]
        try:
            value = cast_function(val, objcol)
        except TypeError:
            value = cast_function(dft, objcol)
        res.setshaderparam(nam, value, typ)

    # Add a default_color, for fallback mechanisms in renderers.
    # By convention, the default color must be in the first parameter of the
    # material.
    par = STD_MATERIALS_PARAMETERS[shadertype][0]
    res.default_color = res.getshaderparam(par.name)
    return res


@functools.lru_cache(maxsize=128)
def _build_passthrough(lines, renderer, default_color):
    """Build passthrough material."""
    res = RenderMaterial("Passthrough")
    res.shader.string = _convert_passthru("\n".join(lines))
    res.shader.renderer = renderer
    res.default_color = default_color
    # pylint: disable=protected-access
    res._partypes["string"] = "str"
    res._partypes["renderer"] = "str"
    res._partypes["default_color"] = "RGBA"
    return res


@functools.lru_cache(maxsize=128)
def _build_fallback(color):
    """Build fallback material (mixed).

    color -- a RGBA tuple color
    """
    try:
        _color = ",".join([str(c) for c in color[:3]])
        _alpha = str(color[3])
    except IndexError:
        _color = "0.8, 0.8, 0.8"
        _alpha = "0.0"

    _rgbcolor = str2rgb(_color)

    # A simpler approach would have been to rely only on mixed material but it
    # leads to a lot of materials definitions in output files which hinders the
    # proper functioning of most of the renderers, so we implement a more
    # selective operation.
    if float(_alpha) == 0:
        # Build diffuse
        shadertype = "Diffuse"
        values = (("Color", _color, _color, "RGB", _rgbcolor),)
    elif float(_alpha) == 1:
        # Build glass
        shadertype = "Glass"
        values = (
            ("IOR", "1.5", "1.5", "float", _rgbcolor),
            ("Color", _color, _color, "RGB", _rgbcolor),
        )
    else:
        # Build mixed
        shadertype = "Mixed"
        values = (
            ("Diffuse.Color", _color, _color, "RGB", _rgbcolor),
            ("Glass.IOR", "1.5", "1.5", "float", _rgbcolor),
            ("Glass.Color", _color, _color, "RGB", _rgbcolor),
            ("Transparency", _alpha, _alpha, "float", _rgbcolor),
        )

    return _build_standard(shadertype, values)


def _get_float(material, param_prefix, param_name, default=0.0):
    """Get float value in material dictionary."""
    return material.get(param_prefix + param_name, default)


PASSTHRU_REPLACED_TOKENS = (
    ("{", "{{"),
    ("}", "}}"),
    ("%NAME%", "{n}"),
    ("%RED%", "{c.r}"),
    ("%GREEN%", "{c.g}"),
    ("%BLUE%", "{c.b}"),
)


@functools.lru_cache(maxsize=128)
def _convert_passthru(passthru):
    """Convert a passthrough string from FCMat format to Python FSML.

    (FSML stands for Format Specification Mini-Language)
    """
    for token in PASSTHRU_REPLACED_TOKENS:
        passthru = passthru.replace(*token)
    return passthru


def printmat(fcdmat):
    """Print a rendering material to a string, in Material Card format.

    This function allows to rebuild a Material Card content from a FreeCAD
    material object, for the Render part.

    Args:
        fcdmat -- a FreeCAD material object (App::MaterialObjectPython)

    Returns:
        a string containing the material in Material Card format
    """

    def keysort(item):
        key, _, keyword = item
        if keyword == "Type":
            rank = 0
        elif keyword in STD_MATERIALS_PARAMETERS:
            rank = 1
        else:
            rank = 2
        return (rank, key)

    items = [
        (i[0], i[1], i[0].split(".")[1])
        for i in fcdmat.Material.items()
        if i[0].startswith("Render.")
    ]
    items.sort(key=keysort)
    lines = [f"{i[0]} = {i[1]}" for i in items]
    print("\n".join(lines))


def clear():
    """Clear functions caches (debug purpose)."""
    _build_fallback.cache_clear()
    _build_passthrough.cache_clear()
    _build_standard.cache_clear()
    _convert_passthru.cache_clear()


# Clear cache when reload module (debug)
clear()
