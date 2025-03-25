from tkinter import *
from tkinter import Tk
from tkinter import filedialog
import csv

class GUI:
    def __init__(self):
        self.root = Tk()
        self.root.wm_title("Runsheet Generator")
        self.makeGUI()

    def makeGUI(self):
        # CSV path entry label
        csvPathEntryLabel = Label(self.root, text="WhenToWork export file")
        csvPathEntryLabel.pack()

        # CSV path entry
        self.csvPathEntry = Entry(self.root)
        self.csvPathEntry.pack()

        # CSV path browse button
        self.csvPathBrowseButton = Button(self.root, text="Browse",
                                          command=self.getCSVPath)
        self.csvPathBrowseButton.pack()

        # Runsheet path entry label
        runsheetPathEntryLabel = Label(self.root,
                                       text="Runsheet output location")
        runsheetPathEntryLabel.pack()

        # Runsheet path entry
        self.runsheetPathEntry = Entry(self.root)
        self.runsheetPathEntry.pack()

        # Runsheet path browse button
        self.runsheetPathBrowseButton = Button(self.root, text="Browse",
                                               command=self.getRunsheetPath)
        self.runsheetPathBrowseButton.pack()

        # Date label
        dateLabel = Label(self.root, text="Date")
        dateLabel.pack()

        # Date listbox
        self.dateListbox = Listbox(self.root)
        self.dateListbox.pack()

        # Confirm button
        self.confirmButton = Button(self.root, text="Create",
                                    command=self.complete)
        self.confirmButton.pack()

        mainloop()

    def getCSVPath(self):
        self.root.csvPath = filedialog.askopenfilename(
            filetypes = (("Comma Separated Values files", ".csv"),
                         ("All files", "*")))
        # Set text of CSV path entry to CSV path
        self.csvPathEntry.delete(0, END)
        self.csvPathEntry.insert(0, self.root.csvPath)

        # Insert CSV file dates into date listbox
        self.insertDatesIntoDateListbox()

    def getRunsheetPath(self):
        self.root.runsheetPath = filedialog.askdirectory()

        # Set text of runsheet path entry to CSV path
        self.runsheetPathEntry.delete(0, END)
        self.runsheetPathEntry.insert(0, self.root.runsheetPath)

    def insertDatesIntoDateListbox(self):
        csvFile = open(self.root.csvPath, 'r')

        # Reader for csvfile
        reader = csv.reader(csvFile, dialect=csv.excel)

        # Header row in CSV file
        HEADER_ROW = next(reader)

        # List of unique date strings from CSV file
        self.dateStrs = []

        # Column containing date strings
        DATE_COLUMN = HEADER_ROW.index("Date")
        # Fill array of unique date strings from CSV file
        for row in reader:
            if row[DATE_COLUMN] not in self.dateStrs:
                self.dateStrs.append(row[DATE_COLUMN])
                
        # Parts of a dateStr
        MONTH_INDEX = 0
        DAY_INDEX = 1
        YEAR_INDEX = 2
                
        # Add leading zeros for sorting where needed
        for i in range(len(self.dateStrs)):
            dateStrParts = self.dateStrs[i].split('/')
            if len(dateStrParts[MONTH_INDEX]) == 1:
                dateStrParts[MONTH_INDEX] = '0' + dateStrParts[MONTH_INDEX]
            if len(dateStrParts[DAY_INDEX]) == 1:
                dateStrParts[DAY_INDEX] = '0' + dateStrParts[1]
            self.dateStrs[i] = dateStrParts[MONTH_INDEX] + '/' + \
                               dateStrParts[DAY_INDEX] + '/' + \
                               dateStrParts[YEAR_INDEX]

        # Sort dates
        self.dateStrs.sort()

        # Insert dates into date listbox
        self.dateListbox.delete(0, END)
        for i in self.dateStrs:
            self.dateListbox.insert(END, i)

    def complete(self):
        currentDateSelectionList = self.dateListbox.curselection()
        currentDateSelectionIndex = currentDateSelectionList[0]
        date = self.dateStrs[currentDateSelectionIndex]
        self.output = (self.root.csvPath, self.root.runsheetPath, date)

        self.root.quit()