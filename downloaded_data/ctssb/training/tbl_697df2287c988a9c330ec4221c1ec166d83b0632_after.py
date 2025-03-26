import fixfmt
import numpy as np

from   tbl.model import Model
from   tbl.view import View, Layout

#-------------------------------------------------------------------------------

def test_lay_out_0():
    mdl = Model()
    mdl.add_col(np.array([ 1,  2,  3]), "foo")
    mdl.add_col(np.array([ 8,  9, 10]), "bar")
    vw = View()
    vw.add_column(0, fixfmt.Number(2))
    vw.add_column(1, fixfmt.String(4))
    vw.show_row_num  = False
    vw.left_border   = "|>"
    vw.separator     = "||"
    vw.right_border  = "<|"

    layout = Layout(vw)
    assert layout.cols == [
        ( 2, 5, 0),
        ( 9, 6,  1),
    ]
    assert layout.text == [
        ( 0, 2, "|>"),
        ( 7, 2, "||"),
        (15, 2, "<|"),
    ]


