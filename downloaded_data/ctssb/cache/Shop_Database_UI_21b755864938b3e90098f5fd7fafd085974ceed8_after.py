import wx
import rus_locale as locale

APP_NAME = 'Shop UI'


class DbList(wx.ListCtrl):
    def __init__(self, parent):
        super(DbList, self).__init__(parent, style=wx.LC_REPORT)

        self.InsertColumn(0, locale.id_col)
        self.InsertColumn(1, locale.name_col)
        self.InsertColumn(2, locale.price_col)


class ShopTab(wx.Panel):
    def __init__(self, parent):
        super(ShopTab, self).__init__(parent)

        button_sizer = wx.GridSizer(4, 1, 10, 0)  # rows, cols, vgap, hgap

        buttons = [wx.Button(self, label=locale.add_button),
                   wx.Button(self, label=locale.delete_button),
                   wx.Button(self, label=locale.to_cart_button)]
        for button in buttons:
            button_sizer.Add(button, 1, wx.EXPAND)

        for func, button in zip([self.on_add, self.on_delete, self.on_to_cart],
                                buttons):
            self.Bind(wx.EVT_BUTTON, func, button)

        db_list = DbList(self)

        outer_sizer = wx.BoxSizer(wx.HORIZONTAL)

        outer_sizer.Add(db_list, 4, wx.EXPAND)
        outer_sizer.AddSpacer(4)
        outer_sizer.Add(button_sizer, 1, wx.TOP)

        self.SetSizer(outer_sizer)

    def on_add(self, e):
        print('on add')

    def on_delete(self, e):
        print('on delete')

    def on_to_cart(self, e):
        print('on to cart')


class CustomerTab(wx.Panel):
    def __init__(self, parent):
        super(CustomerTab, self).__init__(parent)


class ShopNotebook(wx.Notebook):
    def __init__(self, parent):
        super(ShopNotebook, self).__init__(parent)

        self.AddPage(ShopTab(self), locale.shop_tab)
        self.AddPage(CustomerTab(self), locale.customer_tab)


class MainWindow(wx.Frame):
    def __init__(self, parent, title):
        super(MainWindow, self).__init__(parent, title=title)

        self.init_menubar()
        self.init_toolbar()

        panel = wx.Panel(self)
        notebook = ShopNotebook(panel)

        sizer = wx.BoxSizer()
        sizer.Add(notebook, 1, wx.EXPAND)
        panel.SetSizer(sizer)

        self.SetSize((900, 500))  # TODO: make constant
        self.Show(True)

    def init_menubar(self):
        menu_bar = wx.MenuBar()

        # file_menu = wx.Menu() # TODO: add compatibility for non-mac
        # quit_item = file_menu.Append(wx.ID_CLOSE, "Quit {}".format(APP_NAME))
        # menu_bar.Append(file_menu, "File")

        help_menu = wx.Menu()
        about_item = help_menu.Append(wx.ID_ABOUT, "About {}".format(APP_NAME))
        menu_bar.Append(help_menu, "Help")

        self.SetMenuBar(menu_bar)

        self.Bind(wx.EVT_MENU, self.on_about, about_item)

    def init_toolbar(self):
        toolbar = self.CreateToolBar()
        set_tool = toolbar.AddTool(wx.ID_ANY, 'Settings', wx.Bitmap('set.png'))
        toolbar.Realize()

        self.Bind(wx.EVT_TOOL, self.on_set, set_tool)

    def on_about(self, event):
        dlg = wx.MessageDialog(self, "About {}".format(APP_NAME), APP_NAME)
        dlg.ShowModal()
        dlg.Destroy()

    def on_set(self, event):
        pass


def main():
    app = wx.App(False)
    MainWindow(None, APP_NAME)
    app.MainLoop()


if __name__ == '__main__':
    main()
