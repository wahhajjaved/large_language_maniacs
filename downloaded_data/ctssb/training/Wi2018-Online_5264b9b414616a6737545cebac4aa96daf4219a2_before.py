#!/usr/bin/env python3

# Week 4
# Mailroom Assignment - Part 2
#
# Changelog:
# - Added in the use of dictionaries
# - Switched to using switch-case
import sys


donors = {
    'Jimmy Nguyen': [100, 1350, 55],
    'Steve Smith': [213, 550, 435],
    'Julia Norton': [1500, 1500, 1500],
    'Ed Johnson': [150],
    'Elizabeth McBath': [10000, 1200]
}


def print_donor_list():
    """Function simply for looping through the donor list.
    Made into function since it may be called multiple times.
    """
    for donor in donors.keys():
        print(donor)


def get_donor(name):
    """Get donor from the donors dictionary."""
    donor = name.lower()
    for k in donors.keys():
        if donor == k.strip().lower():
            return k
        else:
            return None


def thank_you():
    """Function for Thank you. Prompts for a donors name."""

    while True:
        full_name = input(
            "Please enter a donor's name or type 'list' for list of donors ('menu' to return to menu): ").strip()

        if full_name == 'list':
            print('Below is the current donor list:')
            print_donor_list()
        elif full_name == 'menu':
            return
        else:
            break

    # Enter a donation amount
    while True:
        donation = int(input("Please enter a donation amount. 'menu' to return to original menu: "))
        if donation == 'menu':
            return
        else:
            break

    # Enter a new donor
    donor = get_donor(full_name)
    if donor is None:
        donor = full_name
        donors[donor] = []

    donors[donor].append(donation)

    # Write a thank you for the donor
    print(letter(donor))
    # print('{}, Thank you for your donation in the amount of ${:.2f}'.format(full_name, donation))
    send_letter_file(donor)


def create_report():
    """Function for creating a report."""
    donations = []

    print("{:26s} | {:13s} | {:9s} | {:13s}".format("Donor name", "Total Donation", "Number of Gifts", "Average Gifts"))
    print("-" * 80)

    for donor, gift in donors.items():
        total_given = sum(gift)
        number_gifts = len(gift)
        average_gift = total_given / number_gifts
        donations.append((donor, total_given, number_gifts, average_gift))

    for amount in donations:
        print("{:26s} | {:14.2f} | {:15d} | {:13.2f}".format(*amount))
    print()


def letter(donor):
    """Contents of letter to donors."""
    return """Dear {},\nThank you for your very kind donation of {:.2f}.\n\nIt will be put to very good use.\n\n \t\tSincerely,\n\t\t\t-The Team""".format(
        donor, donors[donor][-1])


def send_letter_file():
    """Write a thank you letter and save to file."""
    # file_name = donor + '.txt'

    for k, v in donors.items():
        file_name = k + '.txt'
        text = letter(k)
        with open(file_name, 'w') as f:
            f.write(text)

    print('Completed creating letters to send out to donors.')


def quit():
    """This function quits the donation management system."""
    return sys.exit('Exiting the system. Please wait...')


def print_header():
    """Prints the menu items to choose from and returns the selection."""

    print('------------------------------------------')
    print('       Donation Management System')
    print('                 v0.1.2\n')
    print('       1: Send A Thank You')
    print('       2: Create A Report')
    print('       3: Send Letters To Everyone')
    print('       4: Quit\n')
    print('------------------------------------------\n')

    selection = int(input('Please select a menu item: '))

    return selection


switcher = {
    1: thank_you,
    2: create_report,
    3: send_letter_file,
    4: quit}


def main():
    """Main mneu of the program."""

    while True:
            switcher[print_header()]()



if __name__ == '__main__':
    main()
