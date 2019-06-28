#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2017 Yorik van Havre <yorik@uncreated.net>              *
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU Lesser General Public License (LGPL)    *
#*   as published by the Free Software Foundation; either version 2 of     *
#*   the License, or (at your option) any later version.                   *
#*   for detail see the LICENCE text file.                                 *
#*                                                                         *
#*   This program is distributed in the hope that it will be useful,       *
#*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
#*   GNU Library General Public License for more details.                  *
#*                                                                         *
#*   You should have received a copy of the GNU Library General Public     *
#*   License along with this program; if not, write to the Free Software   *
#*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#*   USA                                                                   *
#*                                                                         *
#***************************************************************************

# Povray renderer for FreeCAD

# This file can also be used as a template to add more rendering engines.
# You will need to make sure your file is named with a same name (case sensitive)
# That you will use everywhere to describe your renderer, ex: Appleseed or Povray


# A render engine module must contain the following functions:
#
#    writeCamera(camdata): returns a string containing an openInventor camera string in renderer format
#    writeObject(view): returns a string containing a RaytracingView object in renderer format
#    render(project,external=True): renders the given project, external means if the user wishes to open
#                                   the render file in an external application/editor or not. If this
#                                   is not supported by your renderer, you can simply ignore it
#
# Additionally, you might need/want to add:
#
#    Preference page items, that can be used in your functions below
#    An icon under the name Renderer.svg (where Renderer is the name of your Renderer


import FreeCAD
import math
import re


def writeCamera(camdata):


    # this is where you create a piece of text in the format of
    # your renderer, that represents the camera. You can use the contents
    # of obj.Camera, which contain a string in OpenInventor format
    # ex:
    # #Inventor V2.1 ascii
    #
    #
    # PerspectiveCamera {
    #  viewportMapping ADJUST_CAMERA
    #  position 0 -1.3207401 0.82241058
    #  orientation 0.99999666 0 0  0.26732138
    #  nearDistance 1.6108983
    #  farDistance 6611.4492
    #  aspectRatio 1
    #  focalDistance 5
    #  heightAngle 0.78539819
    #
    # }
    #
    # or (ortho camera):
    #
    # #Inventor V2.1 ascii
    #
    #
    # OrthographicCamera {
    #  viewportMapping ADJUST_CAMERA
    #  position 0 0 1
    #  orientation 0 0 1  0
    #  nearDistance 0.99900001
    #  farDistance 1.001
    #  aspectRatio 1
    #  focalDistance 5
    #  height 4.1421356
    #
    # }

    if not camdata:
        return ""
    camdata = camdata.split("\n")
    cam = ""
    pos = [float(p) for p in camdata[5].split()[-3:]]
    pos = FreeCAD.Vector(pos)
    rot = [float(p) for p in camdata[6].split()[-4:]]
    rot = FreeCAD.Rotation(FreeCAD.Vector(rot[0],rot[1],rot[2]),math.degrees(rot[3]))
    tpos = rot.multVec(FreeCAD.Vector(0,0,-1))
    tpos.multiply(float(camdata[10].split()[-1]))
    tpos = pos.add(tpos)
    up = rot.multVec(FreeCAD.Vector(0,1,0))
    cam += "// declares position and view direction\n"
    cam += "// Generated by FreeCAD (http://www.freecadweb.org/)\n"
    cam += "#declare cam_location =  <" + str(pos.x) + "," + str(pos.z) + "," + str(pos.y) + ">;\n"
    cam += "#declare cam_look_at  = <" + str(tpos.x) + "," + str(tpos.z) +"," + str(tpos.y) + ">;\n"
    cam += "#declare cam_sky      = <" + str(up.x) + ","  + str(up.z) + "," + str(up.y) + ">;\n"
    cam += "#declare cam_angle    = 45;\n"
    cam += "camera {\n"
    cam += "  location  cam_location\n"
    cam += "  look_at   cam_look_at\n"
    cam += "  sky       cam_sky\n"
    cam += "  angle     cam_angle\n"
    cam += "  right x*800/600\n"
    cam += "}\n"
    return cam


def writeObject(viewobj):


    # This is where you write your object/view in the format of your
    # renderer. "obj" is the real 3D object handled by this project, not
    # the project itself. This is your only opportunity
    # to write all the data needed by your object (geometry, materials, etc)
    # so make sure you include everything that is needed

    if not viewobj.Source:
        return ""
    objdef = ""
    obj = viewobj.Source
    objname = viewobj.Name
    color = None
    alpha = None
    mat = None
    if viewobj.Material:
        mat = viewobj.Material
    else:
        if "Material" in obj.PropertiesList:
            if obj.Material:
                mat = obj.Material
    if mat:
        if "Material" in mat.PropertiesList:
            if "DiffuseColor" in mat.Material:
                color = mat.Material["DiffuseColor"].strip("(").strip(")").split(",")
                color = str(color[0])+","+str(color[1])+","+str(color[2])
            if "Transparency" in mat.Material:
                if float(mat.Material["Transparency"]) > 0:
                    alpha = str(1.0/float(mat.Material["Transparency"]))
                else:
                    alpha = "1.0"
    if obj.ViewObject:
        if not color:
            if hasattr(obj.ViewObject,"ShapeColor"):
                color = obj.ViewObject.ShapeColor[:3]
                color = str(color[0])+","+str(color[1])+","+str(color[2])
        if not alpha:
            if hasattr(obj.ViewObject,"Transparency"):
                if obj.ViewObject.Transparency > 0:
                    alpha = str(1.0/(float(obj.ViewObject.Transparency)/100.0))
    if not color:
        color = "1.0,1.0,1.0"
    if not alpha:
        alpha = "1.0"
    m = None
    if hasattr(obj,"Group"):
        import Draft,Part,MeshPart
        shps = [o.Shape for o in Draft.getGroupContents(obj) if hasattr(o,"Shape")]
        m = MeshPart.meshFromShape(Shape=Part.makeCompound(shps), 
                                   LinearDeflection=0.1, 
                                   AngularDeflection=0.523599, 
                                   Relative=False)
    elif obj.isDerivedFrom("Part::Feature"):
        import MeshPart
        m = MeshPart.meshFromShape(Shape=obj.Shape, 
                                   LinearDeflection=0.1, 
                                   AngularDeflection=0.523599, 
                                   Relative=False)
    elif obj.isDerivedFrom("Mesh::Feature"):
        m = obj.Mesh
    if not m:
        return ""
    objdef += "#declare " + objname + " = mesh2{\n"
    objdef += "  vertex_vectors {\n"
    objdef += "    " + str(len(m.Topology[0])) + ",\n"
    for p in m.Topology[0]:
        objdef += "    <" + str(p.x) + "," + str(p.z) + "," + str(p.y) + ">,\n"
    objdef += "  }\n"
    objdef += "  normal_vectors {\n"
    objdef += "    " + str(len(m.Topology[0])) + ",\n"
    for p in m.getPointNormals():
        objdef += "    <" + str(p.x) + "," + str(p.z) + "," + str(p.y) + ">,\n"
    objdef += "  }\n"
    objdef += "  face_indices {\n"
    objdef += "    " + str(len(m.Topology[1])) + ",\n"
    for t in m.Topology[1]:
        objdef += "    <" + str(t[0]) + "," + str(t[1]) + "," + str(t[2]) + ">,\n"
    objdef += "  }\n"
    objdef += "}\n"
    
    objdef += "// instance to render\n"
    objdef += "object {" + objname + "\n"
    objdef += "  texture {\n"
    objdef += "    pigment {\n"
    objdef += "      color rgb <" + color + ">\n"
    objdef += "    }\n"
    objdef += "    finish {StdFinish }\n"
    objdef += "  }\n"
    objdef += "}\n"

    return objdef


def render(project,external=True):

    # This is the actual rendering operation

    if not project.PageResult:
        return
    p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Render")
    rpath = p.GetString("PovRayPath","")
    args = p.GetString("PovRayParameters","")
    if not rpath:
        raise
    if args:
        args += " "
    if "RenderWidth" in project.PropertiesList:
        if "+W" in args:
            args = re.sub("\+W[0-9]+","+W"+str(project.RenderWidth),args)
        else:
            args = args + "+W"+str(project.RenderWidth)+" "
    if "RenderHeight" in project.PropertiesList:
        if "+H" in args:
            args = re.sub("\+H[0-9]+","+H"+str(project.RenderHeight),args)
        else:
            args = args + "+H"+str(project.RenderHeight)+" "
    import os
    exe = rpath+" "+args+project.PageResult
    print("Executing "+exe)
    os.system(exe)
    import ImageGui
    imgname = os.path.splitext(project.PageResult)[0]+".png"
    print("Saving image as "+imgname)
    ImageGui.open(imgname)
    return


