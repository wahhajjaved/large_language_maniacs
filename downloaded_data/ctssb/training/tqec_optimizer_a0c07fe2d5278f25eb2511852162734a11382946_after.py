class Edge:
    """
    辺クラス
    """
    def __init__(self, node1, node2, category, id_):
        """
        コンストラクタ

        :param node1 ノード
        :param node2 ノード
        :param category pin or cap or ...
        :param id_ ループ番号
        """
        self._id = id_
        self._type = node1.type
        self._category = category
        self._node1 = node1
        self._node2 = node2
        self._dir = self.__calc_direction()
        self._cross_edge_list = []
        self._color = 0

    def __eq__(self, other):
        return ((self._node1.x + self._node2.x) / 2, (self._node1.y + self._node2.y) / 2,
                (self._node1.z + self._node2.z) / 2) == (other.x, other.y, other.z)

    def __hash__(self):
        return hash((int((self._node1.x + self._node2.x) / 2),
                     int((self._node1.y + self._node2.y) / 2),
                     int((self._node1.z + self._node2.z) / 2)))

    def set_id(self, id_):
        self._id = id_

    def set_type(self, type_):
        self._type = type_

    def set_category(self, category):
        self._category = category

    def set_color(self, color):
        self._color = color

    def add_cross_edge(self, edge):
        self._cross_edge_list.append(edge)

    @property
    def id(self):
        return self._id

    @property
    def type(self):
        return self._type

    @property
    def category(self):
        return self._category

    @property
    def color(self):
        return self._color

    @property
    def x(self):
        return int((self._node1.x + self._node2.x) / 2)

    @property
    def y(self):
        return int((self._node1.y + self._node2.y) / 2)

    @property
    def z(self):
        return int((self._node1.z + self._node2.z) / 2)

    @property
    def node1(self):
        return self._node1

    @property
    def node2(self):
        return self._node2

    @property
    def dir(self):
        return self._dir

    @property
    def cross_edge_list(self):
        return self._cross_edge_list

    def alt_node(self, node):
        if node == self._node1:
            return self._node2
        elif node == self._node2:
            return self._node1
        else:
            assert False

    def is_injector(self):
        if self._category == "pin" or self._category == "cap":
            return True
        return False

    def __calc_direction(self):
        if self._node1.x != self._node2.x:
            direction = 'X'
        elif self._node1.y != self._node2.y:
            direction = 'Y'
        else:
            direction = 'Z'

        return direction

    def dump(self):
        print("type: {} id: {} category: {} ({}, {}, {}) -> ({}, {}, {})".format(self._node1.type, self._id, self._category,
                                                                                 self._node1.x, self._node1.y, self._node1.z,
                                                                                 self._node2.x, self._node2.y, self._node2.z))


class CrossEdge(Edge):
    def __init__(self, node1, node2, category, id_, module_id):
        super().__init__(node1, node2, category, id_)
        self._module_id = module_id
        self._fix = False

    @property
    def module_id(self):
        return self._module_id

    def is_fixed(self):
        return self._fix

    def fix(self):
        self._fix = True

