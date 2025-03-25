from hwtypes import BitVector
from magma.array import Array
from magma.bit import Bit
from magma.bitutils import clog2
from magma.circuit import coreir_port_mapping
from magma.generator import Generator2
from magma.interface import IO
from magma.protocol_type import MagmaProtocol
from magma.t import Type, In, Out
from magma.tuple import Product


class CoreIRCommonLibMuxN(Generator2):
    def __init__(self, N: int, width: int):
        self.name = f"coreir_commonlib_mux{N}x{width}"
        FlatT = Array[width, Bit]
        MuxInT = Product.from_fields("anon", dict(data=Array[N, FlatT],
                                                  sel=Array[clog2(N), Bit]))
        self.io = IO(I=In(MuxInT), O=Out(Array[width, Bit]))
        self.renamed_ports = coreir_port_mapping
        self.coreir_name = "muxn"
        self.coreir_lib = "commonlib"
        self.coreir_genargs = {"width": width, "N": N}
        self.primitive = True
        self.stateful = False

        def simulate(self, value_store, state_store):
            sel = BitVector[clog2(N)](value_store.get_value(self.I.sel))
            out = BitVector[width](value_store.get_value(self.I.data[int(sel)]))
            value_store.set_value(self.O, out)

        self.simulate = simulate


class Mux(Generator2):
    def __init__(self, height: int, T: Type):
        if issubclass(T, MagmaProtocol):
            T = T._to_magma_()
        T_str = str(T).replace("(", "").replace(")", "")\
                      .replace(",", "_").replace("=", "_")\
                      .replace("[", "").replace("]", "").replace(" ", "")
        self.name = f"Mux{height}x{T_str}"
        # TODO: Type must be hashable so we can cache.
        N = T.flat_length()

        io_dict = {}
        for i in range(height):
            io_dict[f"I{i}"] = In(T)
        if height == 2:
            io_dict["S"] = In(Bit)
        else:
            io_dict["S"] = In(Array[clog2(height), Bit])
        io_dict["O"] = Out(T)

        self.io = IO(**io_dict)
        mux = CoreIRCommonLibMuxN(height, N)()
        data = [Array[N, Bit](getattr(self.io, f"I{i}").flatten())
                for i in range(height)]
        mux.I.data @= Array[height, Array[N, Bit]](data)
        if height == 2:
            mux.I.sel[0] @= self.io.S
        else:
            mux.I.sel @= self.io.S
        self.io.O @= T.unflatten(mux.O.ts)


# NOTE(rsetaluri): We monkeypatch this function on to Array due to the circular
# dependency between Mux and Array. See the discussion on
# https://github.com/phanrahan/magma/pull/658.
def _dynamic_mux_select(this, key):
    return Mux(len(this), this.T)()(*this.ts, key)


Array.dynamic_mux_select = _dynamic_mux_select
