# Определить, какое число в массиве встречается чаще всего.

from random import randint

lst = [randint(1, 10) for i in range(500)]
# Тут будет храниться число с наибольшим количеством вхождений
most = {'number': 0, 'count': 0}


def search(lst, most):
    # Базовый случай. Если списка нет, то конец рекурсии
    if lst:
        current = lst[0]
        i = lst.count(current)
        # Проверяем количество вхождений числа, с тем что уже есть в словаре
        if i > most['count']:
            # Если текущее больше, то перезаписывем словарь
            # только не ясно что делать, если есть равные количества,
            # но в ТЗ про это ничего не сказано, поэтому выиграет последний
            most = {'number': lst[0], 'count': i}
        # Удаляем проверенные элементы
        for num in range(i):
            lst.remove(current)

        return search(lst, most)
    else:
        return most


print(search(lst, most))
