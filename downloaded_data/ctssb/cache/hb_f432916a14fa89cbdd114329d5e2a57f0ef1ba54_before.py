import sqlite3


def main():
    db = sqlite3.connect("company.db")
    cursor = db.cursor()

    drop_query = "DROP TABLE IF EXISTS employees"

    create_query = """
    CREATE TABLE employees (
    id INTEGER PRIMARY KEY,
    name TEXT,
    montly_salary INTEGER,
    yearly_bonus INTEGER,
    position TEXT)
    """
    insert_query = "INSERT INTO employees VALUES (?,?,?,?,?)"

    cursor.execute(drop_query)
    cursor.execute(create_query)
    employees = [(None, "Ivan Ivanov", 5000, 10000,  "Software Developer"),
                 (None, "Rado Rado", 500, 0, "Technical Support Intern"),
                 (None, "Ivo Ivo", 10000, 100000, "CEO"),
                 (None, "Petar Petrov", 3000, 1000, "Marketing Manager"),
                 (None, "Maria Georgieva", 8000, 10000, "COO")]
    cursor.executemany(insert_query, employees)
    db.commit()


if __name__ == '__main__':
    main()
