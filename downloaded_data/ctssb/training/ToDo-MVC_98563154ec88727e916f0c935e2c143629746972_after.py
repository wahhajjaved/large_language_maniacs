class HandleItem:

    def __init__(self):
        self.item_list = []

    def add_item(self, item):
        self.item_list.append(item)

    def remove_item(self, index):
        self.item_list.pop(index)

    def get_item_list(self):
        return self.item_list

    def mark_item(self, index):
        self.item_list[index].mark_done()

    def display_item(self, index):
        return self.item_list[index]

    def modify_item(self, index, new_item):
        self.item_list[index] = new_item