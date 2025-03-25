import datetime
from futuregrid.cloud.metric.FGUtility import FGUtility
class Results:
    ''' This generates reports from (start_date) to (t_end_date) in (name) directory as restructuredText files.
        In case that you want to change period of reports, simple change (start_date) and (t_end_date) in this file.
        And run sphinx-build to generate html files. '''

    name = "results"
    docs_ext = ".rst"
    start_date = datetime.date(2011, 11, 01)
    start_date_for_weekly = start_date
    #t_end_date = datetime.date(2012, 07, 26)
    t_end_date = datetime.date.today()
    end_date = start_date + datetime.timedelta(days=6)
    week = datetime.timedelta(weeks=1)
    index_txt = None
    index_filename = name + docs_ext

    docs_path = name + "/"
    indent = "\t"
    newline = "\n"

    def generate_index(self):

        index_txt = ""
        lines = ""

        start_date = self.start_date
        end_date = self.t_end_date

        while(1):
            if start_date > end_date:
                break

            #results.rst (index file)
            each_month = self.indent + self.docs_path + start_date.strftime("%Y-%m") + self.newline
            index_txt = each_month + index_txt 
            year, month, day = start_date.timetuple()[:3]
            if month % 3 == 0:
                quarter = self.indent + self.docs_path + str(year) + "-Q" + str(self.get_quarter(month)) + self.newline
                index_txt = quarter + index_txt
            new_month = month + 1
            start_date = datetime.date(year + (new_month / 13), (new_month % 12) or 12, day)

        #EXCEPTION FOR this month, realtime, and ALL ENTRY
        index_txt = self.indent + self.docs_path + "thismonth" + self.newline + index_txt
        index_txt = self.indent + self.docs_path + "realtime" + self.newline + index_txt
        index_txt = self.indent + self.docs_path + "all" + self.newline + index_txt

        self.index_txt = self.get_index_header() + index_txt

        f = open (self.index_filename, "w")
        f.write(self.index_txt)
        f.close

    def generate_contents(self):
        """ Generate reports in this order: 1) monthly report, 2) weekly reports (normally 4-5 reports per month).
        They are grouped by: 1) nodename e.g. India, Sierra, 2) and platform e.g. eucalyptus, openstack.

        It looks like:

        Report
        ------
            Monthly
            -------
                Jan ...
                ---
                    India
                    -----
                        Eucalyptus
                        ----------
                        Openstack
                        ---------
                    Sierra
                    ------
                        Eucalyptus
                        ----------
                        Openstack
                        ---------
            Weekly
            ------
                1 week
                ------
                    India
                    -----
                    ...
        """

        monthly_report = self.get_content_monthly()
        weekly_report = ""
        month = self.start_date.timetuple()[1]

        while (1):
            if self.start_date > self.t_end_date:
                break
 
            # If a next month comes, generate contents and clear variables for the next
            current_month = self.start_date.timetuple()[1]
            if ((month + 1) % 12 or 12) == current_month:
                contents = monthly_report + weekly_report
                FGUtility.ensure_dir(content_filepath)
                f = open (content_filepath, "w")
                f.write(contents)
                f.close

                # Clear variables
                monthly_report = self.get_content_monthly()
                weekly_report = ""
                month = current_month

            if current_month % 3 == 0:
                contents = self.get_content_quarter()
                content_filename = self.start_date.strftime("%Y-Q") + str(self.get_quarter(current_month))
                content_filepath = self.docs_path + content_filename + self.docs_ext
                FGUtility.ensure_dir(content_filepath)
                f = open (content_filepath, "w")
                f.write(contents)
                f.close
 
            content_filename = self.start_date.strftime("%Y-%m")
            content_filepath = self.docs_path + content_filename + self.docs_ext
           
            self.end_date = self.start_date + datetime.timedelta(days=6)
            if (self.start_date_for_weekly + (10 * self.week)) == self.start_date:
                self.start_date_for_weekly = self.start_date_for_weekly + self.week

            # stacking up weekly reports
            weekly_report += self.get_content_weekly()
 
            self.start_date = self.start_date + self.week
            ## END OF LOOP

        contents = monthly_report + weekly_report
        FGUtility.ensure_dir(content_filepath)
        f = open (content_filepath, "w")
        f.write(contents)
        f.close

    def get_content_quarter(self):
        width = 800
        height = 600
        start_date = str(self.start_date)
        end_date = str(self.end_date)
        current_month = self.start_date.timetuple()[1]
        month_n_year2 = "Q" + str(self.get_quarter(current_month))
        month_n_year = month_n_year2 + self.start_date.strftime(" %Y")
        month = self.start_date.strftime("%Y-") + month_n_year2

        number = 1
        metric = "count"
        platform = "eucalyptus"
        nodename = "india"

        main_title = month_n_year + self.newline + \
                "========================================" + self.newline

        main_title += "Quarterly report (" + month_n_year2 + ")" + self.newline + \
                "----------------------------------------" + self.newline

        main_title += self.get_content_sub_header(nodename, platform)
 
        src = "data/%(month)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
        title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(month_n_year)s on %(nodename)s"
        content = main_title + self.get_chart() % vars()
        content = content % vars()

        number += 1
        src = "data/%(month)s/%(nodename)s/%(platform)s/user/FGGoogleMotionChart.html"
        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "runtime"
        title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(month_n_year)s on %(nodename)s"
        src = "data/%(month)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "count"

        src = "data/%(month)s/%(nodename)s/%(platform)s/%(metric)s/master-detailhighcharts.html"
        title = "Figure %(number)s. Total %(metric)s of VMs submitted on %(nodename)s in %(month_n_year)s"
 
        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "runtime"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "ccvm_cores"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "ccvm_mem"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "ccvm_disk"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "count_node"

        src = "data/%(month)s/%(nodename)s/%(platform)s/%(metric)s/columnhighcharts.html"
        title = "Figure %(number)s. Total VMs count per node cluster for %(month_n_year)s on %(nodename)s"
 
        content = content + (self.get_chart() % vars()) % vars()

        # Data for OpenStack on India is only available after 06/01/2012
        if self.start_date >= datetime.date(2012, 6, 01):
            number += 1
            metric = "count"
            platform = "openstack"
            nodename = "india"

            main_title = content + self.get_content_sub_header(nodename, platform)
     
            src = "data/%(month)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
            title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(month_n_year)s on %(nodename)s"
            content = main_title + self.get_chart() % vars()
            content = content % vars()

            number += 1
            metric = "runtime"
            title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(month_n_year)s on %(nodename)s"

            content = content + (self.get_chart() % vars()) % vars()

        # Data on Sierra is only available after 05/01/2012
        if self.start_date >= datetime.date(2012, 5, 01):
            number += 1
            metric = "count"
            platform = "eucalyptus"
            nodename = "sierra"

            main_title = content + self.get_content_sub_header(nodename, platform)
     
            src = "data/%(month)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
            title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(month_n_year)s on %(nodename)s"
            content = main_title + self.get_chart() % vars()
            content = content % vars()

            number += 1
            metric = "runtime"
            title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(month_n_year)s on %(nodename)s"

            content = content + (self.get_chart() % vars()) % vars()

            number += 1
            metric = "count"

            src = "data/%(month)s/%(nodename)s/%(platform)s/%(metric)s/master-detailhighcharts.html"
            title = "Figure %(number)s. Total %(metric)s of VMs submitted on %(nodename)s in %(month_n_year)s"
     
            content = content + (self.get_chart() % vars()) % vars()

            number += 1
            metric = "runtime"

            content = content + (self.get_chart() % vars()) % vars()

            number += 1
            metric = "ccvm_cores"

            content = content + (self.get_chart() % vars()) % vars()

            number += 1
            metric = "ccvm_mem"

            content = content + (self.get_chart() % vars()) % vars()

            number += 1
            metric = "ccvm_disk"

            content = content + (self.get_chart() % vars()) % vars()

            number += 1
            metric = "count_node"

            src = "data/%(month)s/%(nodename)s/%(platform)s/%(metric)s/columnhighcharts.html"
            title = "Figure %(number)s. Total VMs count per node cluster for %(month_n_year)s on %(nodename)s"
     
            content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "count"
        platform = "nimbus"
        nodename = "hotel"

        main_title = content + self.get_content_sub_header(nodename, platform)
 
        src = "data/%(month)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
        title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(month_n_year)s on %(nodename)s"
        content = main_title + self.get_chart() % vars()
        content = content % vars()

        number += 1
        metric = "runtime"
        title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(month_n_year)s on %(nodename)s"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "count"
        nodename = "alamo"

        main_title = content + self.get_content_sub_header(nodename, platform)
 
        src = "data/%(month)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
        title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(month_n_year)s on %(nodename)s"
        content = main_title + self.get_chart() % vars()
        content = content % vars()

        number += 1
        metric = "runtime"
        title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(month_n_year)s on %(nodename)s"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "count"
        nodename = "foxtrot"

        main_title = content + self.get_content_sub_header(nodename, platform)
 
        src = "data/%(month)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
        title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(month_n_year)s on %(nodename)s"
        content = main_title + self.get_chart() % vars()
        content = content % vars()

        number += 1
        metric = "runtime"
        title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(month_n_year)s on %(nodename)s"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "count"
        nodename = "sierra"

        main_title = content + self.get_content_sub_header(nodename, platform)
 
        src = "data/%(month)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
        title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(month_n_year)s on %(nodename)s"
        content = main_title + self.get_chart() % vars()
        content = content % vars()

        number += 1
        metric = "runtime"
        title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(month_n_year)s on %(nodename)s"

        content = content + (self.get_chart() % vars()) % vars()

        return content


    def get_content_monthly(self):
        width = 800
        height = 600
        start_date = str(self.start_date)
        end_date = str(self.end_date)
        month_n_year = self.start_date.strftime("%B %Y")
        month_n_year2 = self.start_date.strftime("%m/%Y")
        month = self.start_date.strftime("%Y-%m")

        number = 1
        metric = "count"
        platform = "eucalyptus"
        nodename = "india"

        main_title = month_n_year + self.newline + \
                "========================================" + self.newline

        main_title += "Monthly report (" + month_n_year2 + ")" + self.newline + \
                "----------------------------------------" + self.newline

        main_title += self.get_content_sub_header(nodename, platform)
 
        src = "data/%(month)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
        title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(month_n_year)s on %(nodename)s"
        content = main_title + self.get_chart() % vars()
        content = content % vars()

        number += 1
        src = "data/%(month)s/%(nodename)s/%(platform)s/user/FGGoogleMotionChart.html"
        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "runtime"
        title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(month_n_year)s on %(nodename)s"
        src = "data/%(month)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "count"

        src = "data/%(month)s/%(nodename)s/%(platform)s/%(metric)s/master-detailhighcharts.html"
        title = "Figure %(number)s. Total %(metric)s of VMs submitted on %(nodename)s in %(month_n_year)s"
 
        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "runtime"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "ccvm_cores"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "ccvm_mem"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "ccvm_disk"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "count_node"

        src = "data/%(month)s/%(nodename)s/%(platform)s/%(metric)s/columnhighcharts.html"
        title = "Figure %(number)s. Total VMs count per node cluster for %(month_n_year)s on %(nodename)s"
 
        content = content + (self.get_chart() % vars()) % vars()

        # Data for OpenStack on India is only available after 06/01/2012
        if self.start_date >= datetime.date(2012, 6, 01):
            number += 1
            metric = "count"
            platform = "openstack"
            nodename = "india"

            main_title = content + self.get_content_sub_header(nodename, platform)
     
            src = "data/%(month)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
            title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(month_n_year)s on %(nodename)s"
            content = main_title + self.get_chart() % vars()
            content = content % vars()

            number += 1
            metric = "runtime"
            title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(month_n_year)s on %(nodename)s"

            content = content + (self.get_chart() % vars()) % vars()

        # Data on Sierra is only available after 05/01/2012
        if self.start_date >= datetime.date(2012, 5, 01):
            number += 1
            metric = "count"
            platform = "eucalyptus"
            nodename = "sierra"

            main_title = content + self.get_content_sub_header(nodename, platform)
     
            src = "data/%(month)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
            title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(month_n_year)s on %(nodename)s"
            content = main_title + self.get_chart() % vars()
            content = content % vars()

            number += 1
            metric = "runtime"
            title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(month_n_year)s on %(nodename)s"

            content = content + (self.get_chart() % vars()) % vars()

            number += 1
            metric = "count"

            src = "data/%(month)s/%(nodename)s/%(platform)s/%(metric)s/master-detailhighcharts.html"
            title = "Figure %(number)s. Total %(metric)s of VMs submitted on %(nodename)s in %(month_n_year)s"
     
            content = content + (self.get_chart() % vars()) % vars()

            number += 1
            metric = "runtime"

            content = content + (self.get_chart() % vars()) % vars()

            number += 1
            metric = "ccvm_cores"

            content = content + (self.get_chart() % vars()) % vars()

            number += 1
            metric = "ccvm_mem"

            content = content + (self.get_chart() % vars()) % vars()

            number += 1
            metric = "ccvm_disk"

            content = content + (self.get_chart() % vars()) % vars()

            number += 1
            metric = "count_node"

            src = "data/%(month)s/%(nodename)s/%(platform)s/%(metric)s/columnhighcharts.html"
            title = "Figure %(number)s. Total VMs count per node cluster for %(month_n_year)s on %(nodename)s"
     
            content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "count"
        platform = "nimbus"
        nodename = "hotel"

        main_title = content + self.get_content_sub_header(nodename, platform)
 
        src = "data/%(month)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
        title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(month_n_year)s on %(nodename)s"
        content = main_title + self.get_chart() % vars()
        content = content % vars()

        number += 1
        metric = "runtime"
        title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(month_n_year)s on %(nodename)s"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "count"
        nodename = "alamo"

        main_title = content + self.get_content_sub_header(nodename, platform)
 
        src = "data/%(month)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
        title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(month_n_year)s on %(nodename)s"
        content = main_title + self.get_chart() % vars()
        content = content % vars()

        number += 1
        metric = "runtime"
        title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(month_n_year)s on %(nodename)s"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "count"
        nodename = "foxtrot"

        main_title = content + self.get_content_sub_header(nodename, platform)
 
        src = "data/%(month)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
        title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(month_n_year)s on %(nodename)s"
        content = main_title + self.get_chart() % vars()
        content = content % vars()

        number += 1
        metric = "runtime"
        title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(month_n_year)s on %(nodename)s"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "count"
        nodename = "sierra"

        main_title = content + self.get_content_sub_header(nodename, platform)
 
        src = "data/%(month)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
        title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(month_n_year)s on %(nodename)s"
        content = main_title + self.get_chart() % vars()
        content = content % vars()

        number += 1
        metric = "runtime"
        title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(month_n_year)s on %(nodename)s"

        content = content + (self.get_chart() % vars()) % vars()

        return content

    def get_content_weekly(self):
        width = 800
        height = 600
        start_date = str(self.start_date)
        end_date = str(self.end_date)

        number = 1
        metric = "count"
        platform = "eucalyptus"
        nodename = "india"

        main_title = self.newline +  self.start_date.strftime("%m/%d/%Y") + " - " + self.end_date.strftime("%m/%d/%Y") + self.newline + \
                    "------------------------------------------------------------" + self.newline + \
                    ""
 
        main_title += self.get_content_sub_header(nodename, platform)

        src = "data/%(end_date)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
        title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(start_date)s  ~ %(end_date)s on %(nodename)s"
        content = main_title + self.get_chart() % vars()
        content = content % vars()

        number += 1
        metric = "runtime"
        title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(start_date)s  ~ %(end_date)s on %(nodename)s"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "count_node"

        src = "data/%(end_date)s/%(nodename)s/%(platform)s/%(metric)s/columnhighcharts.html"
        title = "Figure %(number)s. Total VMs count per node cluster for %(start_date)s  ~ %(end_date)s on %(nodename)s"
 
        content = content + (self.get_chart() % vars()) % vars()

        # Data for OpenStack on India is only available after 06/01/2012
        if self.start_date >= datetime.date(2012, 6, 01):
            number += 1
            metric = "count"
            platform = "openstack"
            nodename = "india"

            main_title = self.get_content_sub_header(nodename, platform)
     
            src = "data/%(end_date)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
            title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(start_date)s ~ %(end_date)s on %(nodename)s"
            content = content + main_title + self.get_chart() % vars()
            content = content % vars()

            number += 1
            metric = "runtime"
            title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(start_date)s ~ %(end_date)s on %(nodename)s"

            content = content + (self.get_chart() % vars()) % vars()

        # Data on Sierra is only available after 05/01/2012
        if self.start_date >= datetime.date(2012, 5, 01):

            number += 1
            metric = "count"
            platform = "eucalyptus"
            nodename = "sierra"

            main_title = self.get_content_sub_header(nodename, platform)

            src = "data/%(end_date)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
            title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(start_date)s  ~ %(end_date)s on %(nodename)s"
            content = content + main_title + self.get_chart() % vars()
            content = content % vars()

            number += 1
            metric = "runtime"
            title = "Figure %(number)s. Total %(metric)s hour of VMs submitted per user for %(start_date)s  ~ %(end_date)s on %(nodename)s"

            content = content + (self.get_chart() % vars()) % vars()

            number += 1
            metric = "count_node"

            src = "data/%(end_date)s/%(nodename)s/%(platform)s/%(metric)s/columnhighcharts.html"
            title = "Figure %(number)s. Total VMs count per node cluster for %(start_date)s  ~ %(end_date)s on %(nodename)s"
     
            content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "count"
        platform = "nimbus"
        nodename = "hotel"

        main_title = self.get_content_sub_header(nodename, platform)
 
        src = "data/%(end_date)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
        title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(start_date)s ~ %(end_date)s on %(nodename)s"
        content = content + main_title + self.get_chart() % vars()
        content = content % vars()

        number += 1
        metric = "runtime"
        title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(start_date)s ~ %(end_date)s on %(nodename)s"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "count"
        nodename = "alamo"

        main_title = self.get_content_sub_header(nodename, platform)
 
        src = "data/%(end_date)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
        title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(start_date)s ~ %(end_date)s on %(nodename)s"
        content = content + main_title + self.get_chart() % vars()
        content = content % vars()

        number += 1
        metric = "runtime"
        title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(start_date)s ~ %(end_date)s on %(nodename)s"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "count"
        nodename = "foxtrot"

        main_title = self.get_content_sub_header(nodename, platform)
 
        src = "data/%(end_date)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
        title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(start_date)s ~ %(end_date)s on %(nodename)s"
        content = content + main_title + self.get_chart() % vars()
        content = content % vars()

        number += 1
        metric = "runtime"
        title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(start_date)s ~ %(end_date)s on %(nodename)s"

        content = content + (self.get_chart() % vars()) % vars()

        number += 1
        metric = "count"
        nodename = "sierra"

        main_title = self.get_content_sub_header(nodename, platform)
 
        src = "data/%(end_date)s/%(nodename)s/%(platform)s/user/%(metric)s/barhighcharts.html"
        title = "Figure %(number)s. Total %(metric)s of VMs submitted per user for %(start_date)s ~ %(end_date)s on %(nodename)s"
        content = content + main_title + self.get_chart() % vars()
        content = content % vars()

        number += 1
        metric = "runtime"
        title = "Figure %(number)s. Total %(metric)s (hour) of VMs submitted per user for %(start_date)s ~ %(end_date)s on %(nodename)s"

        content = content + (self.get_chart() % vars()) % vars()

        return content

    def get_index_header(self):
        res =   "Cloud Metric Results" + self.newline + \
                "====================" + self.newline + \
                "We have collected cloud utilization data from Eucalyptus on FutureGrid such as India and Sierra resources and provide weekly and monthly reports to show usage of system resources measured by FG Cloud Metric." + self.newline + \
                self.newline + \
                "Contents:" + self.newline + \
                self.newline + \
                ".. toctree::" + self.newline + \
                self.indent + ":maxdepth: 2" + self.newline + \
                self.newline 
        return res

    def get_content_sub_header(self, nodename, platform):
        res = self.newline + "Results for " + platform + " on " + nodename + ".futuregrid.org" + self.newline + \
                "^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^" + self.newline
        return res
    
    def get_chart(self):
        res =   "" + self.newline + \
                ".. raw:: html" + self.newline + \
                "" + self.newline + \
                self.indent + "<div style=\"margin-top:10px;\">" + self.newline + \
                self.indent + "<iframe width=\"%(width)s\" height=\"%(height)s\" src=\"%(src)s\" frameborder=\"0\"></iframe>" + self.newline + \
                self.indent + "</div>" + self.newline + \
                self.indent + "%(title)s" + self.newline
                
        return res

    def get_quarter(self, mon):
        return (mon - 1)//3 + 1

def main():
    result = Results()
    result.generate_index()
    result.generate_contents()

if __name__ == "__main__":
    main()
