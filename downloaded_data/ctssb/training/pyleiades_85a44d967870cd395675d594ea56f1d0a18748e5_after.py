import pandas as pd
from utils.load_data import load_dataset
from utils.eia_codes import name_to_code, date_to_code


class EClass:
    
    """
    Collect energy data for a user-defined energy source.
    
    Retrieves data from the specified energy source according to specific 
    attributes, such as energy consumed per decade, per year, or all years in 
    which more than a certain amount of energy was consumed from that source.
    Use this class to extract and return pure data from the dataset.
    """
    
    def __init__(self,energy_source,stat_type='consumption',data=pd.DataFrame(),data_date='default'):
        """
        Receive energy source and collect corresponding data.
        
        Parameters
        ----------
        energy_source : str
            The energy source to be pulled from the dataset.
        stat_type : str
            The type of statistic to be collected ('production', 'consumption',
            'import', or 'export').
        data : DataFrame, optional
            The EIA dataset from which to pull information. Must be three columns:
            date, energy quantity, and energy code. If omitted, use the default
            dataset.
        data_date : str
            The date identifier of the dataset; 'default' and 'newest' are 
            current options (the ability to call specific dataset dates to be
            added).
        """
        # Determine Ecode from energy source name
        E_code = name_to_code(energy_source)

        # Use default dataset if dataset argument is omitted
        if data.empty:
            data = load_dataset(dataset_date=data_date,dataset_type=stat_type)
       
        # Isolate this energy's data, separate frequencies, and format the data
        self.E_data = self._isolate_energy(E_code,data)
        self.monthly_data, self.yearly_data = self._sep_freqs(self.E_data)
        for data_df in self.monthly_data,self.yearly_data:
            data_df.set_index('Date_code',inplace=True)

        self.freq_errmsg = 'Frequency "{}" is not compatible with this dataset; see documentation for permissible frequencies.' 
        self.extr_errmsg = 'Input "{}" is not recognized as an extrema; try "max" or "min"' 

    def _isolate_energy(self,E_code,data):
        """
        Isolate one type of energy in the given dataset.

        Parameters
        ----------
        E_code : int
            The energy code corresponding to the energy source to be selected.
        data : DataFrame
            The dataset containing all energy values across energy sources.

        Returns
        -------
        E_data : DataFrame
            A trimmed version of the original dataset, now with only the
            selected energy source. The energy code column is removed.
        """
        E_data = data[data.E_code == E_code]
        E_data = E_data[['Date_code','Value']]
        return E_data

    def _sep_freqs(self,data):
        """
        Separate the data into monthly and yearly intervals.

        Parameters
        ----------
        data : DataFrame
            The dataset to be partitioned into monthly and yearly intervals.

        Returns
        -------
        monthly_data : DataFrame
            A subset of the data with the energy values reported monthly.
        yearly_data : DataFrame
            A subset of the data with the energy values reported yearly.
        """
        # Monthly totals
        monthly_data = data[data.Date_code.str[-2:]!='13']
        monthly_data = monthly_data.assign(Date=monthly_data.Date_code)
        # Yearly totals
        yearly_data = data[data.Date_code.str[-2:]=='13']
        yearly_data = yearly_data.assign(Date=yearly_data.Date_code.str[:-2])
        return monthly_data,yearly_data

    def _daterange(self,data,start_date,end_date):
        """
        Resize the dataset to cover only the date range specified.
        
        Parameters
        ----------
        data : DataFrame
            A dataframe containing the data to be resized. The index must be
            in the format of the EIA date code ('YYYYMM').
        start_date, end_date : str
            The dataset start/end dates (both inclusive) as strings ('YYYYMM').
            
        Returns
        -------
        bound_data : DataFrame
            A dataframe corresponding to the specified date range.
        """
        # Use dataset default dates unless otherwise specified by the user
        if start_date == None: start_date = data.index.min()
        else: start_date = date_to_code(start_date) 
        if end_date == None: end_date = data.index.max()
        else: end_date = date_to_code(end_date)

        # Adjust dataset boundaries 
        half_bounded_data = data[data.index >= start_date]
        bounded_data = half_bounded_data[half_bounded_data.index <= end_date]
        return bounded_data

    def totals(self,freq='yearly',start_date=None,end_date=None,):
        """
        Get the energy statistic totals over a given period.
        
        This method aggregates energy statistic totals according to a user 
        defined frequency--either monthly, yearly, or cumulatively. Data is
        collected for the entire dataset unless specific dates are given.
        When dates are provided, the totals are only returned on that time 
        interval, with inclusive starting and ending dates. If data at the
        specified frequency does not exist for the entire interval, the interval
        will be automatically adjusted to fit the available data in the 
        interval. Cumulative totals use yearly data, and so only include data up
        until the last complete year.
        
        Parameters
        ----------
        freq : str
            The frequency for gathering totals ('monthly','yearly',or
            'cumulative').
        start_date, end_date : str
            The user specified starting and ending dates for the dataset 
            (both inclusive); for 'monthly', acceptable formats are 'YYYYMM',
            'YYYY-MM', or 'MM-YYYY' (dashes can be substituted for periods,
            underscores, or forward slashes); for 'yearly' or 'cumulative',
            give only the full year, 'YYYY'.
            
        Returns
        -------
        totals_data : DataFrame, float
            A dataframe containing totals in the specified interval at the 
            given frequency, a floating point number if a cumulative sum.
        """
        # Bound data at requested frequency by start and end dates
        if freq == 'monthly':
            full_data = self.monthly_data
        elif freq == 'yearly' or freq == 'cumulative':
            full_data = self.yearly_data
        else:
            raise ValueError(self.freq_errmsg.format(freq))
        totals_data = self._daterange(full_data,start_date,end_date)

        # For cumulative totals, take the sum
        if freq == 'cumulative':
            totals_data = totals_data.Value.sum()
        return totals_data
        
    def extrema(self,extremum,freq='monthly',start_date=None,end_date=None):
        """
        Get the maximum/minimum energy consumed over a given period.
        
        Parameters
        ----------
        extremum : str
            The exteme value to be found ('max' or 'min').
        freq : str
            The frequency for checking extrema ('monthly' or 'yearly').
        start_date, end_date : str
            The user specified starting and ending dates for the dataset 
            (both inclusive); for 'monthly', acceptable formats are 'YYYYMM',
            'YYYY-MM', or 'MM-YYYY' (dashes can be substituted for periods,
            underscores, or forward slashes); for 'yearly' or 'cumulative',
            give only the full year, 'YYYY'.
        
        Returns
        -------
        extreme_value : float
            A dataframe giving the specified extreme value and the date of
            occurrence for that value.
        extrema_date : string
            A string representation of the month in which the extreme value
            occurred (format 'YYYY' or 'YYYYMM')
        """
        # Bound data by start and end dates
        if freq == 'monthly':
            full_data = self.monthly_data
        elif freq == 'yearly':
            full_data = self.yearly_data
        else:
            raise ValueError(self.freq_errmsg.format(freq))
        extremum_data = self._daterange(full_data,start_date,end_date)

        # Select max or min
        extremum = extremum.lower()[:3]
        if extremum == 'max':
            extremum_val = extremum_data.Value.max()
        elif extremum == 'min':
            extremum_val = extremum_data.Value.min()
        else:
            raise ValueError(self.extr_errmsg.format(extremum))
        extremum_data = extremum_data[extremum_data.Value == extremum_val]
        extreme_value = extremum_data['Value'][0]
        extremum_date = extremum_data['Date'][0]
        return extreme_value,extremum_date

    #def more_than(self,amount,start_date,end_date,interval):
        """
        Get data for time intervals where more than the given amount of energy was consumed.
        
        Parameters
        ----------
        amount: float
            The lower boundary (exclusive) for which data may be included in the dataset.
        start_date, end_date : str
            The user specified dataset starting and ending dates (both inclusive); 
            acceptable formats are 'YYYYMM', 'YYYY-MM', or 'MM-YYYY'. Dashes ("-") can 
            be substituted for periods ("."), underscores ("_"), or forward slashes ("/").
        interval : str
            The time intervals considered for extrema comparison ('yearly',or 'monthly').
        """
        
    
    
    """
    Additonal potential options to add:
        - average yearly energy consumed
        - average seasonal energy consumed
        - consolidate date range selection and monthly/yearly/cumulative selection into a _formatdata method
    """
 

