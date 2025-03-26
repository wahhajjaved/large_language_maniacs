from unittest import TestCase

from kata.board import Board
from kata.task import Task

TITLE = 'irrelevant_title'


class TestBoard(TestCase):

    def test_is_public(self):
        board = Board(title=TITLE, is_public=True)
        assert isinstance(board, Board)
        assert board.is_public

    def test_is_not_public_when_false(self):
        board = Board(title=TITLE, is_public=False)
        assert isinstance(board, Board)
        assert board.is_public is False

    def test_is_not_public_when_None(self):
        board = Board(title=TITLE, is_public=None)
        assert isinstance(board, Board)
        assert board.is_public is False

    def test_add_tag_list(self):
        board = Board(title=TITLE)
        tags = ['tag_1', 'tag_2', 'tag_3']
        board.add_tags(tags)
        assert board.tags == tags

    def test_add_single_tag(self):
        board = Board(title=TITLE)
        tag = 'tag_1'
        board.add_tags(tag)
        assert board.tags == [tag]

    def test_add_none_empty_tags(self):
        board = Board(title=TITLE)
        board.add_tags('TAG')
        board.add_tags('')
        board.add_tags(None)
        assert board.tags == ['TAG']

    def test_columns(self):
        board1 = Board(title=TITLE, columns=['ToDo', 'Done'])

        board2 = Board(title=TITLE)
        board3 = Board(title=TITLE)

        board2.add_column('Doing')
        board3.add_column('OnHold')
        board2.add_column('Archived')

        assert board1.columns == ['ToDo', 'Done']
        assert board2.columns == ['Doing', 'Archived']
        assert board3.columns == ['OnHold']

    def test_add_task(self):
        board = Board(title=TITLE, columns=['ToDo', 'Done'])
        task = Task('a_task')
        board.add_task(column='ToDo', task=task)

        assert board.get_tasks() == [task]

    def test_add_tasks(self):
        board = Board(title=TITLE, columns=['ToDo', 'Done'])
        task1 = Task('a_task_1')
        task2 = Task('a_task_2')
        board.add_task(column='ToDo', task=task1)
        board.add_task(column='ToDo', task=task2)

        assert board.get_tasks() == [task1, task2]

    def test_archive_all(self):
        board = Board(title=TITLE, columns=['ToDo', 'Done'])
        board.add_task(column='ToDo', task=Task('a_task_1'))
        board.add_task(column='ToDo', task=Task('a_task_2'))
        board.add_task(column='Done', task=Task('a_task_3'))

        archived = board.archive_all()

        assert archived
        for task in board.get_task():
            assert task.archived

    def test_archive_all_by_column(self):
        board = Board(title=TITLE, columns=['ToDo', 'Done'])
        archived = board.archive_all(columns=['ToDo'])
        board.add_task(column='ToDo', task=Task('a_task_1'))
        board.add_task(column='ToDo', task=Task('a_task_2'))
        board.add_task(column='Done', task=Task('a_task_3'))

        assert archived
        for task in board.get_task():
            if task.name != 'a_task_3':
                assert task.archived
            else:
                assert not task.archived
