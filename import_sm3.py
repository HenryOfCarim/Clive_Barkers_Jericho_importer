import bpy
import struct
import os
from mathutils import Matrix, Vector

GAME_TO_BLENDER = Matrix((
    (-1, 0, 0, 0),
    (0, 0, -1, 0),
    (0, 1, 0, 0),
    (0, 0, 0, 1),
))
BLENDER_TO_GAME = GAME_TO_BLENDER.inverted()


# Idea for future refactoring
class MeshSM3():
    def __init__(self):
        self.modelname = ""
        self.face_indices = []
        self.uv = []
        self.vertex_groups = []
        self.grupy = []
        self.group_bounds = None
        self.mesh_bounds = None
        self.unknown_bounds_data = None
        self.mat_id = None


class ImportSM3():
    def __init__(self, file, filepath):
        self.file = file
        self.filepath = filepath
        self.modelname = os.path.basename(filepath).split('.')[0]
        self.armature_ob = None
        self.newarm = None
        self.meshes = {}  # name | face indices + UV | groups | grupy - bone id?
        self.mesh_name = ""
        self.grupy = []
        self.groups = []
        self.namebone = ""
        self.bonenames = []
        self.id_object = 0
        self.mesh = None
        self.obj = None
        self.vertexy = None
        self.faceslist = None
        self.uvcoord = None

    def read_string(self, long):
        string = ''
        for j in range(0, long): 
            lit = struct.unpack('c', self.file.read(1))[0]
            if ord(lit) != 0:
                string += lit.decode('latin')
                if len(string) > 100:
                    break
        return string

    def read_byte(self, n):
        return struct.unpack(n*'b', self.file.read(n))

    def read_ubyte(self, n):
        return struct.unpack(n*'B', self.file.read(n))

    def read_short(self, n):
        return struct.unpack(n*'h', self.file.read(n*2))

    def read_ushort(self, n):
        return struct.unpack(n*'H', self.file.read(n*2))

    def read_int(self, n):
        return struct.unpack(n*'i', self.file.read(n*4))

    def read_float(self, n):
        return struct.unpack(n*'f', self.file.read(n*4))

    def material_name(self, mat_id):
        if self.armature_ob is not None and self.armature_ob.data is not None:
            armature_name = self.armature_ob.data.name
        else:
            armature_name = self.modelname
        return f"{armature_name}-mat-{mat_id}"

    def create_material(self, m):
        self.read_string(8), self.read_int(1)  # MAT
        print('MATERIAL ', self.read_string(self.read_int(1)[0]))
        mat_name = self.material_name(m)
        try:
            mat = bpy.data.materials[mat_name]
        except KeyError:
            mat = bpy.data.materials.new(mat_name)
        mat.use_nodes = True
        mat.blend_method = 'CLIP'
        self.read_ubyte(44), self.read_int(3)  # NOTHING
        return mat

    def make_armature(self):
        namefile = self.filepath.split(os.sep)[-1].split('.')[0]
        armature = bpy.data.armatures.new(namefile+'-arm')
        self.armature_ob = bpy.data.objects.new(namefile + '-armobj', armature)
        bpy.context.collection.objects.link(self.armature_ob)
        bpy.context.view_layer.objects.active = self.armature_ob
        self.armature_ob.data.display_type = 'STICK'

    def make_bones(self):
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        self.newarm = self.armature_ob.data
        data = self.read_int(6)
        self.namebone = self.read_string(self.read_int(1)[0])[-25:]
        self.newarm.edit_bones.new(self.namebone)
        self.bonenames[data[1]] = self.namebone
        nameparent = self.read_string(self.read_int(1)[0])[-25:]
        # print("parent bone is {}".format(nameparent))
        if len(nameparent) > 0:
            try:
                parent = self.newarm.edit_bones[nameparent]
            except KeyError:
                parent = None
            if parent is not None:
                self.newarm.edit_bones[self.namebone].parent = parent
        self.read_float(8)
        # bonematrix = Matrix([self.read_float(4), self.read_float(4), self.read_float(4), self.read_float(4)])
        x = self.read_float(4)
        y = self.read_float(4)
        z = self.read_float(4)
        w = self.read_float(4)
        imported_matrix = Matrix([x, y, z, w])
        bonematrix = imported_matrix.transposed()
        bonematrix = GAME_TO_BLENDER @ bonematrix @ BLENDER_TO_GAME
        self.read_float(23)
        bone = self.newarm.edit_bones[self.namebone]
        bone.length = 0.1
        bone.matrix = bonematrix

    def read_mesh_data(self, num):
        self.grupy = []
        print(self.namebone + '=' + str(num))
        self.meshes[self.namebone + '='+str(num)] = []
        print('ADD FACES')
        self.meshes[self.namebone + '='+str(num)].append(self.read_faces())
        self.read_string(4)  # LFVF
        print('ADD VERTEXES UVCOORD')
        self.meshes[self.namebone + '='+str(num)].append(self.read_vertices())
        print('ADD VERTEX GROUPS')
        self.meshes[self.namebone + '='+str(num)].append(self.groups)
        # data = self.read_int(2)
        num_vgroups = self.read_int(1)[0]
        unk_num = self.read_int(1)[0]
        print(self.namebone + '='+str(num))
        print('VERTEX GROUPS ARE', num_vgroups, unk_num)
        for k in range(num_vgroups):
            vtx_groups = self.read_ushort(1)[0]
            self.grupy.append(vtx_groups)
        print('ADD GRUPY')
        self.meshes[self.namebone+'='+str(num)].append(self.grupy)
        self.read_int(2), self.read_int(2), self.read_int(2), self.read_int(2)
        data = self.read_int(2)
        if data[1] == 0:
            data1 = self.read_int(2)
            print('making limited groups', data1)
            for m in range(data1[0]):
                num_bones = self.read_ubyte(1)[0]
                vtx_groups = self.read_ubyte(3)
                weights = self.read_float(3)
                # num_bones 1-3, supports only 3 bones per vertex
                self.groups.append([num_bones, vtx_groups, weights])
        data = self.read_int(2)
        for m in range(data[0]):
            self.read_ubyte(data[1])
        mat_id = self.read_int(2)
        self.read_int(1)
        group_bounds = self.read_float(6)
        mesh_bounds = self.read_float(6)
        unknown_bounds_data = self.read_float(4)
        self.meshes[self.namebone+'='+str(num)].append({
            "group_bounds": group_bounds,
            "mesh_bounds": mesh_bounds,
            "unknown": unknown_bounds_data,
        })
        # add id_mat
        self.meshes[self.namebone+'='+str(num)].append(mat_id[0])

    def read_materials(self):
        # Original hadcoded "dds" folder for textures
        # dir_images = os.path.dirname(self.filepath) + os.sep +'dds' + os.sep
        dir_images = os.path.dirname(self.filepath) + os.sep
        dir_images = dir_images.lower()
        num_mat = self.read_int(1)[0]
        print('num_mat =', num_mat)
        for m in range(num_mat):
            mat = self.create_material(m)
            mat.use_nodes = True
            mat.blend_method = 'CLIP'
            shader_node_grp = mat.node_tree.nodes.get("Principled BSDF")
            link = mat.node_tree.links.new
            while (True):
                data = self.read_int(1)[0]
                if data == 0:
                    pass
                elif data == 1:
                    self.read_string(8), self.read_int(1)
                    # name_image = self.read_string(self.read_int(1)[0]).split('/')[-1].split('.')[0]
                    name_image = os.path.basename(self.read_string(self.read_int(1)[0]))
                    name_image = os.path.splitext(name_image)[0] + ".dds"
                    name_image = name_image.lower()
                    texture_node = mat.node_tree.nodes.new('ShaderNodeTexImage')
                    texture_node.location = (140, -230)
                    try:
                        texture_node.image = bpy.data.images.load(dir_images+name_image)
                    except:
                        print("no textures {}".format(dir_images+name_image))
                    if '-d' in name_image:
                        # Diffuse
                        link(texture_node.outputs['Color'], shader_node_grp.inputs['Base Color'])
                        link(texture_node.outputs['Alpha'], shader_node_grp.inputs['Alpha'])
                        texture_node.location = (-600, 360)
                    if '-m' in name_image:
                        # Specular
                        texture_node.image.colorspace_settings.name = 'Non-Color'
                        invert_node = mat.node_tree.nodes.new('ShaderNodeInvert')
                        invert_node.location = (-500, 60)

                        link(texture_node.outputs['Alpha'], invert_node.inputs['Color'])
                        link(invert_node.outputs['Color'], shader_node_grp.inputs['Roughness'])
                        texture_node.location = (-830, 30)
                    if '-b' in name_image:
                        # Normal
                        texture_node.image.colorspace_settings.name = 'Non-Color'
                        # # RGB nodes
                        normal_separate = mat.node_tree.nodes.new('ShaderNodeSeparateRGB')
                        normal_separate.name = "separate_normal"
                        normal_separate.label = "Separate Normal"
                        normal_separate.location = (-860, -460)

                        normal_combine = mat.node_tree.nodes.new('ShaderNodeCombineRGB')
                        normal_combine.name = "combine_normal"
                        normal_combine.label = "Combine Normal"
                        normal_combine.location = (-700, -360)

                        # # Normal node
                        normal_map = mat.node_tree.nodes.new('ShaderNodeNormalMap')  # create normal map node
                        normal_map.inputs[0].default_value = 1.5
                        normal_map.location = (-510, -260)

                        link(texture_node.outputs['Color'], normal_separate.inputs[0])
                        link(texture_node.outputs['Alpha'], normal_combine.inputs['R'])
                        link(normal_separate.outputs['G'], normal_combine.inputs['G'])
                        link(normal_combine.outputs[0], normal_map.inputs['Color'])
                        link(normal_map.outputs['Normal'], shader_node_grp.inputs['Normal'])

                        texture_node.location = (-1190, -330)
                    data = self.read_int(4)
                    if data[3] != 0:
                        break
                    self.read_ubyte(11)
                else:
                    seek = self.file.tell()
                    self.file.seek(seek-4)
                    break

    def readdata(self):
        # global bonenames,meshes,id_object
        self.bonenames = []
        id_object = 0
        self.read_string(4)  # magic word
        self.read_int(1)  # unk01
        self.read_ubyte(4)  # unk bytes
        self.read_float(2)  # unk_floats
        self.read_string(4)  # unk_str SCN
        self.read_int(3)  # unk_int
        str_size = self.read_int(1)[0]
        self.read_string(str_size)  # unk_str_01
        self.read_int(1)  # unk_int_01
        self.read_string(4)  # unk_str_02 INI
        data = self.read_int(3)  # 0, 1 , 31
        # print(data)
        for m in range(data[2]):
            long = (self.read_int(1)[0])
            print("Stings header ", self.read_string(long))
        self.read_float(15)
        self.read_materials()
        seek = self.file.tell()
        self.file.seek(seek-36)
        print("Node start adress ", self.file.tell())
        node_data = self.read_int(2)
        print('==== MAKING NODES ====')
        print('begin----------', node_data[0])
        print('num nodes------', node_data[1])
        for m in range(node_data[1]):
            self.bonenames.append('')
        for m in range(node_data[1]):
            self.make_bones()
            long = self.read_int(1)[0]
            # INI node?
            for n in range(long):
                unk_node_str = self.read_string(4)
                print("Unknows node id is ", unk_node_str)
                data = self.read_int(3)
                # Bone adjustments
                for k in range(data[2]):
                    long = self.read_int(1)[0]
                    node_str = self.read_string(long)
                    print("Node string is {}".format(node_str))
            long = self.read_int(1)[0]
            for n in range(long):
                id_object += 1
                self.read_int(1)
                num = 0
                self.groups = []
                while (True):
                    name = self.read_string(4)
                    if name == 'CAM':
                        self.read_int(5), self.read_float(14)
                        break
                    elif name == 'MD3D':
                        self.read_mesh_data(num)
                        data = self.read_int(1)[0]
                        if data == 0:
                            break
                        num += 1
                    else:
                        break
        print(struct.unpack('i', self.file.read(4))[0])
        print('KONIEC AT OFFSET ', self.file.tell())

    def read_faces(self):
        faceslist = []
        data = self.read_int(3)
        self.read_string(data[2])
        data = self.read_int(2)
        for m in range(data[0]):
            v = self.read_ushort(3)
            faceslist.append(v)
        return faceslist

    def read_vertices(self):
        vertexes = []
        uvcoord = []
        data = self.read_int(4)
        vtx_format = self.read_int(1)[0]
        num_vtx = self.read_int(1)[0]
        print("read vertex data", data)
        if vtx_format == 48:
            for m in range(num_vtx):
                v = self.read_float(3)
                vertexes.append(tuple(GAME_TO_BLENDER.to_3x3() @ Vector(v)))
                self.read_float(3)
                u = self.read_float(1)[0]
                v = self.read_float(1)[0]
                uvcoord.append([u, 1-v])
                self.read_float(4)

        if vtx_format == 80:
            for m in range(num_vtx):
                v = self.read_float(3)
                vertexes.append(tuple(GAME_TO_BLENDER.to_3x3() @ Vector(v)))
                self.read_float(3)
                u = self.read_float(1)[0]
                v = self.read_float(1)[0]
                uvcoord.append([u, 1-v])
                self.read_float(6)
                self.read_float(2)
                self.read_float(4)

        return vertexes, uvcoord

    def draw_all(self):
        for self.mesh_name in self.meshes:
            mesh_data = self.meshes[self.mesh_name]
            self.faceslist = mesh_data[0]
            self.vertexy = mesh_data[1][0]
            self.uvcoord = mesh_data[1][1]
            self.groups = mesh_data[2]  # data for all vertices
            self.grupy = mesh_data[3]  # all vertices?
            mat_id = mesh_data[5]
            self.build_mesh(self.mesh_name)
            if len(self.groups) == 0:
                bone_name = self.mesh_name.split('=')[0]
                matrix = self.make_right_mesh_position(bone_name)

                self.obj.parent = self.armature_ob
                self.obj.parent_type = 'BONE'
                self.obj.parent_bone = bone_name
                self.obj.matrix_world = matrix
            else:
                self.make_vertex_group()
                armature_modifier = self.obj.modifiers.new(name="Armature Modifier", type='ARMATURE')
                armature_modifier.object = self.armature_ob
            material_name = self.material_name(mat_id)
            print("Material name is", material_name)
            material = bpy.data.materials.get(material_name)
            if material:
                self.mesh.materials.append(material)

    def build_mesh(self, name):
        self.mesh = bpy.data.meshes.new(name)
        faces = [(face[0], face[2], face[1]) for face in self.faceslist]
        self.mesh.from_pydata(self.vertexy, [], faces)
        if len(self.uvcoord) != 0:
            self.uv()
        self.obj = bpy.data.objects.new(name, self.mesh)
        # The addon doesn't import normals so fake smoothing instead
        for polygon in self.mesh.polygons:
            polygon.use_smooth = True
        if self.armature_ob is not None:
            self.obj.parent = self.armature_ob
        bpy.context.collection.objects.link(self.obj)

    def uv(self):
        if not self.mesh.uv_layers:
            self.mesh.uv_layers.new(name="uv")
        uv_layer = self.mesh.uv_layers.active.data
        # Assign UV coordinates to each loop
        for poly in self.mesh.polygons:
            for loop_index in range(poly.loop_start, poly.loop_start + poly.loop_total):
                vertex_index = self.mesh.loops[loop_index].vertex_index
                uv_layer[loop_index].uv = self.uvcoord[vertex_index]

    def make_vertex_group(self):
        for v_id in range(len(self.grupy)):
            data_id = self.grupy[v_id]
            num_bones, bone_ids, weights = self.groups[data_id]
            vertex_groups = self.obj.vertex_groups
            for i in range(num_bones):
                bone_id = bone_ids[i]
                weight = weights[i]
                bone_name = self.bonenames[bone_id]
                try:
                    vertex_groups[bone_name].add([v_id], weight, 'REPLACE')
                except KeyError:
                    self.obj.vertex_groups.new(name=bone_name)
                    vertex_groups[bone_name].add([v_id], weight, 'REPLACE')

    def make_right_mesh_position(self, bone_name):
        bone = self.armature_ob.data.bones.get(bone_name)

        if bone is None:
            print(f"Bone '{bone_name}' not found in armature '{self.armature_ob.name}'")
            return Matrix.Identity(4)  # Return identity matrix if bone not found

        return self.armature_ob.matrix_world @ bone.matrix_local
