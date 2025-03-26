import pandas as pd
import numpy as np

from dateutil.relativedelta import relativedelta
from tkinter.filedialog import askopenfilename
from tkinter.filedialog import asksaveasfilename

class IdentifyPlacementsPostShelterStay:
    """
    This class will process the Placement Report v.4 + Entry to Shelter.xlsx report that is an ART
    product. As of the writing of this script the ART report is located in the following location:
    Public Folder/City of Portland/TPI/W.I.P./

    The goal is to create a list of addresses for participants who were placed into housing within
    3 months of a shelter stay.
    """
    def __init__(self, file):
        """
        Initializes the class but also processes the raw excel file into three distinct data frames
        removing rows from each of the data frames where the relevant date fields are blank.

        :file: the location of the Placement Report v.4 + Entry to Shelter.xlsx
        """
        self.file = file
        self.raw_entries = pd.read_excel(self.file, sheet_name="Entries to Shelter").dropna(
            axis=0,
            how="any",
            subset=["Entry Exit Exit Date"]
        )
        self.raw_placements = pd.read_excel(self.file, sheet_name="Placement Data").dropna(
            axis=0,
            how="any",
            subset=["Placement Date(3072)"]
        )
        self.raw_addresses = pd.read_excel(self.file, sheet_name="Address Data").dropna(
            axis=0,
            how="any",
            subset=["Placement Date(833)"]
        )

    def find_related_data(
        self,
        entries,
        placements,
        addresses
    ):
        """
        Compare the entries dataframe and the placement dataframe. Return a placement dataframe with
        at least one related row in the entries dataframe.  Also return an entry dataframe with at
        least a single value in the placement dataframe, and an address dataframe with at least a
        single value in the placement dataframe.

        :entries: The raw_entries dataframe
        :placements: The raw_placements dataframe
        :addresses:  The raw_adresses dataframe
        """
        # add a line dropping entry rows if they don't have an exit date
        valid_entries = entries[entries["Client Uid"].isin(placements["Client Uid"])]
        valid_placements = placements[placements["Client Uid"].isin(valid_entries["Client Uid"])]
        valid_addresses = addresses[addresses["Client Uid"].isin(valid_placements)]
        return valid_entries, valid_placements, valid_addresses

    def check_for_entry_3_months_prior_to_placement(self, entry_data, placement_data):
        """
        Compare shelter exit dates and placement dates looking for an entry exit exit date that is
        no more than 3 months prior to the placement date.  Return the resulting placement
        dataframe.

        :entry_data: An entry dataframe processed to only contain rows with a Client Uid in the
        placement dataframe
        :placement_data: A placement dataframe processed to only contain rows with a Client Uid in the
        entries dataframe
        """
        merged = pd.merge(placement_data, entry_data, how="outer", on="Client Uid")
        merged["Entry Exit Entry Date"] = merged["Entry Exit Entry Date"].dt.date
        merged["Entry Exit Exit Date"] = merged["Entry Exit Exit Date"].dt.date
        merged["Placement Date(3072)"] = merged["Placement Date(3072)"].dt.date
        merged["3mo Pre Placement"] = merged["Placement Date(3072)"] + relativedelta(months=-3)
        in_range = merged[
            (
                (merged["Entry Exit Exit Date"] < merged["Placement Date(3072)"]) |
                (merged["Entry Exit Exit Date"] == merged["Placement Date(3072)"])
            ) &
            (
                (merged["Entry Exit Exit Date"] > merged["3mo Pre Placement"]) |
                (merged["Entry Exit Exit Date"] == merged["3mo Pre Placement"])
            )
        ]
        return in_range

    def find_closest_address(self, placement_data):
        """
        Compare the addresses dataframe to the placements dataframe returned by the
        check_for_entry_3_months_prior_to_placement method and return a dataframe of addresses that
        have a start date which is closest to, but not greater than, the placement date.

        :placement_data: The placement dataframe output by the
        check_for_entry_3_months_prior_to_placement methodself.
        :address_data: The address data_frame that is produced by the find_related_data method.
        """
        merged = pd.merge(placement_data, self.raw_addresses, how="outer", on="Client Uid")
        merged["Placement Date(833)"] = merged["Placement Date(833)"].dt.date
        in_range = merged[
            (merged["Placement Date(833)"] == merged["Placement Date(3072)"]) |
            (merged["Placement Date(833)"] < merged["Placement Date(3072)"])
        ].sort_values(by="Placement Date(833)", ascending=False).drop_duplicates(subset="Client Uid")
        return self.raw_addresses[
            self.raw_addresses["Recordset ID (61-recordset_id)"].isin(
                in_range["Recordset ID (61-recordset_id)"]
            )
        ]

    def process(self):
        """
        Call the other methods in this class in sequence and return the resulting dataframe.
        Sequence: find_related_data, check_for_entry_3_months_prior_to_placement,
        find_closest_address
        """
        entry_data, placement_data, address_data = self.find_related_data(
            self.raw_entries,
            self.raw_placements,
            self.raw_addresses
        )
        post_shelter_placement = self.check_for_entry_3_months_prior_to_placement(
            entry_data,
            placement_data
        )
        return find_closest_address(post_shelter_placement)

if __name__ == "__main__":
    # report location: \\tproserver\Reports\OneOff\DavidKatz\FY17-18\Placements Post Shelter Stay
    report = askopenfilename(
        title="Open the Placement Report v.4 + Entry to Shelter.xlsx ART report"
    )
    run = IdentifyPlacementsPostShelterStay(report)
    report = run.process()
    writer = pd.ExcelWriter(
        asksaveasfilename(
            title="Save the Shelter Related Placement Report",
            defaultextension=".xlsx",
            initialfile="Shelter Related Placement Report"
        ),
        engine="xlsxwriter"
    )
