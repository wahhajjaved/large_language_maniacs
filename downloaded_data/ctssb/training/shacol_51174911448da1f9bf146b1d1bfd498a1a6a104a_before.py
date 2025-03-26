import sys, os, git
import pymysql as mariadb
import climenu

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)
import shacol

db_location = '85.255.0.154'
git_repo = git.repo.Repo(root_dir)

@climenu.menu()
def set_bit_length():
    '''Select bit length and input string'''
    print("Select from these\n"
          "4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, ...")
    climenu.settings.back_values[0] = climenu.get_user_input("Enter input bit length ")
    user_input = climenu.get_user_input("Insert string, that would be hashed as input for Shacol (leave it blank, if you want to use default input): ")
    if user_input != "":
        climenu.settings.back_values[99] = user_input
        print("input OK")
    else:
        print("input failed, nothing happened")


@climenu.menu()
def set_bit_range():
    '''Select bit range'''
    print("Select from these\n"
          "4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, ...")
    climenu.settings.back_values[1] = climenu.get_user_input("Enter start bit length ")
    climenu.settings.back_values[2] = climenu.get_user_input("Enter max bit length ")
@climenu.menu()
def select_methods():
    '''Select methods'''
    print("Methods availible:\n"
          "1. String method\n"
          "2. Int method\n"
          "3. DB set method (Redis)\n")
    user_input = int(input("Select method number: "))
    if user_input == 1:
        climenu.settings.back_values[3] = 1
    elif user_input == 2:
        climenu.settings.back_values[4] = 1
    elif user_input == 3:
        climenu.settings.back_values[5] = 1
    else:
        print("wrong input, nothing happened")

def main():
    for i in range(0, 100):
        climenu.settings.back_values.insert(i, None)
    climenu.run()
    menu_values = climenu.settings.back_values

    if menu_values[99] != None:
        inputValue = menu_values[99]
    else:
        inputValue = root_dir + "/hash.txt"
    shacolInstance = shacol.Shacol(int(menu_values[0]), inputValue)
    end_iter = int(menu_values[2]) + 1
    for i in range(int(menu_values[1]), end_iter, 4):
        shacolInstance.changeBitLength(i)
        shacolInstance.getInfo()
        if int(menu_values[3]) == 1:
            results = shacolInstance.findCollisionStr()
            method = "String method"
            dbInsert(results, method, i)
        if int(menu_values[4]) == 1:
            results = shacolInstance.findCollisionInt()
            method = "Int method"
            dbInsert(results, method, i)
        if int(menu_values[5]) == 1:
            results = shacolInstance.findCollisionWithDBSet()
            method = "Method with DB Set"
            dbInsert(results, method, i)
        if int(menu_values[6]) == 1:
            results = shacolInstance.findCollisionIntBF()
            method = "Int BF"
            dbInsert(results, method, i)


def dbInsert(results, method, bits):
    db_conn = mariadb.connect(host=db_location, user='shacol_django_u', password='Aim4Uusoom9ea8',
                              database='shacol_django')
    cursor = db_conn.cursor()
    add_collision = ("INSERT INTO website_collision"
                    "(hash_order, input_hash, total_time, cycles, coll_hash, firstTemp, lastTemp, total_memory, test_method, bits, git_revision)"
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)")

    data_collision = (int(results["indexOfLast"]), results["inputHash"], results["time"], int(results["cyclesBetCol"]), results["collisionHash"], results["firstTemp"], results["lastTemp"], results["dataStructConsum"], method, int(bits), git_repo.git.describe())
    cursor.execute(add_collision, data_collision)

    db_conn.commit()
    cursor.close()
    db_conn.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print('\nInterrupted... Terminating')
        sys.exit()

"""
INDEX - print(results["index"])
INPUT_HASH - print(results["inputHash"])
TOTAL_TIME - print(results["time"])
CYCLES - print(results["cycles"])
COLL_HASH - print(results["collisionHash"])
TEST_METHOD - "INT", "STR", "DB"
BITS - print(results["bits"])
GIT_REVISION - subprocess.check_output(["git", "describe"])
"""
