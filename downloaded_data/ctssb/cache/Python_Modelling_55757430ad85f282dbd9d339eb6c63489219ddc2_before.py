#/usr/bin/python
from __future__ import division, print_function
from sknn.backend import lasagne

import sys

import numpy as np
#from scipy.spatial import cKDTree as KDTree
# http://docs.scipy.org/doc/scipy/reference/spatial.html

import MySQLdb

#from sklearn import datasets, cross_validation
from sknn.mlp import Regressor, Layer
from sklearn.svm import SVR
from sklearn.pipeline import Pipeline
from sklearn.cross_validation import train_test_split
from sklearn import preprocessing
from sklearn.grid_search import GridSearchCV
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from resources import data_from_db, create_mesh, classify_hour

from resources import NW_BOUND,SW_BOUND,NE_BOUND, create_mean_value_grid

import pickle
from datetime import datetime

# do you want to do zero mean analysis and get the mean and std per hour?
run_zero_mean_analysis = False
# do you want to use a nn to train?
use_nn = True


if not run_zero_mean_analysis:
    do_optimisation = False
    # do you want to run the hour simplification feature?
    use_hour_simplification_feature = True
    # do you want to run an existing model for nn or svm
    run_existing_model = False

    if run_existing_model:
        pickle_model = False
    else:
        pickle_model = True

images_base_dir = "../images/"

data_table = "samplesGridData"


run_existing_model = False
pickle_model = False


def zero_mean_analysis():
    """

    Function to generate data for zero mean analysis. The result return the mean, 
    std and non zero grid count for each hour. 
    When using this, pipe the output out to a file. e.g. python train_model.py > file.txt
    
    """
    #start data and end data from populate estimates script
    start_date = datetime(2013,3,1)
    end_date = datetime(2015,11,1)

    # Open database connection
    db = MySQLdb.connect("localhost","pollution","pollution","pollution_monitoring" )

    # prepare a cursor object using cursor() method
    cursor = db.cursor()

    sql_str = """ INSERT IGNORE INTO CV_values (datetime, date, time, weekdays, dayoftheweek, mean_fixed)
                    SELECT 
                        date as datetime, DATE_FORMAT(date,"%Y-%m-%d") AS date, DATE_FORMAT(date,"%H") as time, if(WEEKDAY(date)<5, true, false) AS weekdays, WEEKDAY(date) AS dayoftheweek, avg(co) as mean_fixed
                    FROM 
                        Samples 
                    WHERE 
                        user_id = 2 and date between "{0}" AND "{1}" AND co IS NOT NULL AND latitude is not null and longitude is not null AND (latitude <= {2} AND latitude >= {3}) AND (longitude >= {4} AND longitude <= {5})
                    GROUP BY
                        date
                    ORDER BY
                        date asc """.format(start_date, end_date, NW_BOUND[0], SW_BOUND[0], NW_BOUND[1], NE_BOUND[1])

    cursor.execute(sql_str)
    db.close()

    #retrieve and group the data by datetime (hour)
    sql_string = """select datetime, date, time, dayoftheweek, grid_location, co from {0}  order by datetime asc, grid_location asc; """.format(data_table)
    #print(sql_string)
    df_mysql = data_from_db(sql_string)

    grouped = df_mysql.groupby(['datetime'])

    X = [] 
    y = []

    stats = []

    #iterate through and group by datetime
    for name, group in grouped:
        X.append([group['dayoftheweek'].iloc[0], group['time'].iloc[0]])
        assert(len(group['co'].values.flatten()) == 10000)
        y.append(group['co'].values.flatten())

        date_vals = group[['datetime', 'date', 'time', 'dayoftheweek']].values[0]
        query_datetime = date_vals[0]

        #get data for an hour
        select_str = """SELECT 
                            date as datetime, DATE_FORMAT(date,"%Y-%m-%d") AS date, DATE_FORMAT(date,"%H") as time, if(WEEKDAY(date)<5, true, false) AS weekdays, WEEKDAY(date) AS dayoftheweek, latitude, longitude, user_id, co 
                        FROM 
                            Samples 
                        WHERE 
                            user_id != 2 and date between "{0}" and date_add("{0}", interval 1 hour) and co is not null and latitude is not null and longitude is not null AND (latitude <= {1} AND latitude >= {2}) AND (longitude >= {3} AND longitude <= {4}) AND co > 0 AND co < 60
                        ORDER BY
                            date asc """.format(query_datetime, NW_BOUND[0], SW_BOUND[0], NW_BOUND[1], NE_BOUND[1])
        df_mysql = data_from_db(select_str, verbose=False, exit_on_zero=False)

        #check the number of bins populated
        _, non_zero_grid_count = create_mean_value_grid(df_mysql)


        #update status array
        # use degrees of freedom = 0, i.e. without Bessel's correction
        stats.append(np.append(date_vals, [group['co'].mean(), group['co'].std(ddof=0), non_zero_grid_count]))


    #write all the rows of stats
    for row in stats:
        print(';'.join(["%s" % i for i in row]))

    sys.exit()

def use_existing_model():
    """

    Function is used if flag is set to use existing model.
    The model is set based on the current svm or nn model available in
    a pickle file in the same directory as this script.

    """

    #no need to predict the full grid if you're using nn
    #if not use_nn:
    predict_full_grid = True
    #else:
    #    predict_full_grid = False


    #Assume there exists existing model of name "current_model" pickle file
    if use_nn:
        file_name = "nn_current_model"
    else:
        file_name = "svm_current_model"

    fileObject = open(file_name,'rb')
    pipeline = pickle.load(fileObject)

    #use the datetime specified and get the rows of data
    #weekend date
    #specified_date = "2013-05-26 12:"
    #weekday date
    specified_date = "2015-09-03 12:"
    print("date is ", specified_date)
    sql_string = """select * from {1} where datetime like "{0}%" order by datetime asc, grid_location_row, grid_location_col asc; """.format(specified_date, data_table)

    print(sql_string)
    df_mysql = data_from_db(sql_string)


    y_true = []
    y_pred = []

    for _, row in df_mysql.iterrows():

        if use_hour_simplification_feature:
            hour_feature = classify_hour(row['time'])
        else:
            hour_feature = row['time']

        X = [[row['weekdays'], hour_feature, row['season'], row['grid_location_row'], row['grid_location_col'], row['co_liverpool'], row['co_prospect'], row['co_chullora'], row['co_rozelle']]]
        y = row['co']


        #print X_train
        X = np.float64(X)
        y = np.float64(y)

        y_true.append(y)
        y_pred.append(pipeline.predict(X)[0])

    if predict_full_grid:
        y_pred_full = []

        for i in xrange(100):
            for j in xrange(100):
                X[0][3] = i 
                X[0][4] = j
                y_val = pipeline.predict(X)[0]
                y_pred_full.append(y_val)
                #print(i, j, y_val)

    #create the mesh here
    id_name = specified_date.replace(":","")
    #prediction_name = "_pred_zeroMean"
    #estimates_name = "_estimates_zeroMean"

    if not use_nn:
        prediction_name = "_pred_full_zeroMean_svm"
        y_pred_full = np.float64(y_pred_full)
        create_mesh(y_pred_full.reshape(100,100), images_base_dir + id_name + prediction_name, title_name="predicted_full_grid_with_svm")
    else:
        prediction_name = "_pred_full_zeroMean_nn"
        y_pred_full = np.float64(y_pred_full)
        create_mesh(y_pred_full.reshape(100,100), images_base_dir + id_name + prediction_name, title_name="predicted_full_grid_with_nn")
        #create_mesh(y_true.reshape(100,100), images_base_dir + id_name + estimates_name, title_name="estimates_nn")
        #create_mesh(y_pred.reshape(100,100), images_base_dir + id_name + prediction_name, title_name="predicted_nn")

    #print some stats
    #print("Mean squared error is: ", -mean_squared_error(y_true, y_pred))
    print("Mean absolute error is: ", abs(mean_absolute_error(y_true, y_pred)))
    #print("R^2 score is: ", -r2_score(y_true, y_pred, multioutput='uniform_average'))
    print(pipeline.get_params())

    #save a log of the parameters of the last run using the existing model
    with open(images_base_dir + id_name + "_existing_model_params.txt", "w") as text_file:
        text_file.write(specified_date+"\n")
        text_file.write(sql_string+"\n")
        text_file.write(str(pipeline)+"\n")
        text_file.write(str(pipeline.get_params())+"\n")
        #text_file.write("Mean squared error is: {0}\n".format(-mean_squared_error(y_true, y_pred)))
        text_file.write("Mean absolute error is: {0}\n".format(abs(mean_absolute_error(y_true, y_pred))))
        #text_file.write("R^2 score is: {0}\n".format(-r2_score(y_true, y_pred, multioutput='uniform_average')))
        
    fileObject.close()
    sys.exit()

def optimise(pipeline, X_train, y_train):
    """

    This currently works for neural networka only.
    Set the parameter grid below to explore different parameters in a grid search.

    TODO: Implement this for svm


    """

    if use_nn:
        param_grid = {
            'nn__learning_rate': np.arange(0.001, 0.1, 0.01),
            'nn__hidden0__units': np.arange(75,155,10), 
            #'nn__hidden1__units': np.arange(5000,25000,5000), 
            #'nn__weight_decay': np.arange(0.00005, 0.00015, 0.00005),
            #'nn__hidden0__type': ["Rectifier", "Sigmoid", "Tanh"]
        }
    else:
        raise Exception("Need to specify parameter grid for grid search for svm")
    
    from sklearn.cross_validation import ShuffleSplit

    #search through the parameters
    gs = GridSearchCV(pipeline, param_grid = param_grid, scoring="mean_absolute_error", cv=ShuffleSplit(len(X_train), test_size=0.33, n_iter=1, random_state=0))
    gs.fit(X_train, y_train)

    print(gs.best_params_)
    print("Best score is {0}".format(-gs.best_score_))

    #Pickle results
    if pickle_model:
        if use_nn:
            file_name = "nn_optimal_model"
        else:
            file_name = "svm_optimal_model"
        fileObject = open(file_name,'wb')
        pickle.dump(gs, fileObject)
        fileObject.close()

    log_file_name = "log_optimisation.txt"
    logfileObject = open(log_file_name,'wb')
    logfileObject.write(gs.best_params_)
    logfileObject.write("Best score is {0}".format(gs.best_score_))
    logfileObject.write(gs.grid_scores_)
    logfileObject.close()

    print("Optimal Model and log saved")
    #y_true, y_pred = y_test, pipeline.predict(X_test)
    #print("Mean squared error is: ", mean_squared_error(y_true, y_pred))
    #1 is good, 0 means no relationship, for negative values, the mean of the data provides a better fit to the outcomes than the fitted function values
    #print("R^2 score is: ", r2_score(y_true, y_pred, multioutput='uniform_average'))
    sys.exit()

def main():
    """ 
    
    Implement the training of the model. This decides if nn or svn is run, 
    or we choose to instead run the zero mean analysis. These variables are 
    set below the imports, globally.
    
    """


    if run_zero_mean_analysis:
        zero_mean_analysis()

    if run_existing_model:
        use_existing_model()

    ##################################
    ###### Train Model here
    ##################################

    #name of the image file
    name = "time_vs_co_averages"
    name = images_base_dir + name

    #retrieve sql data for the period required
    sql_string = """select * from {0}  order by datetime asc, grid_location_row, grid_location_col asc; """.format(data_table)
    df_mysql = data_from_db(sql_string)


    X = [] 
    y = []

    #if use_nn:
    #    #output predicted here is 10000 co values
    #    grouped = df_mysql.groupby(['datetime'])
    #    #iterate through and group by datetime
    #    for name, group in grouped:
    #        X.append([group['dayoftheweek'].iloc[0], group['time'].iloc[0], group['season'].iloc[0]])
    #        assert(len(group['co'].values.flatten()) == 10000)
    #        y.append(group['co'].values.flatten())
    #else:

    #output predicted here is one co value
    for _, row in df_mysql.iterrows():
        if use_hour_simplification_feature:
            hour_feature = classify_hour(row['time'])
        else:
            hour_feature = row['time']

        X.append([row['weekdays'], hour_feature, row['season'], row['grid_location_row'], row['grid_location_col'], row['co_liverpool'], row['co_prospect'], row['co_chullora'], row['co_rozelle']])
        y.append(row['co'])

    #print X_train
    Z = np.float64(X)
    y = np.float64(y)

    X_train, X_test, y_train, y_test = train_test_split(Z, y, test_size =0 , random_state=0)
    if use_nn:
        pipeline = Pipeline([
            ('min/max scaler', preprocessing.MinMaxScaler(feature_range=(0.0, 1.0))),
            ('nn', Regressor(
                layers=[
                    Layer("Rectifier", units=150),
                    #Layer("Rectifier", units=100),
                    Layer("Linear")
                    ],
                learning_rate=0.001,
                #regularize='L2', 
                #weight_decay=0.0000005,
                n_iter=70,
                valid_size=.33,
                verbose=True))
             ])

        param_grid = {
            'nn__learning_rate': [0.001],#np.arange(0.001, 0.040, 0.010),
            'nn__hidden0__units': [150],#np.arange(500,5000,1000), 
           }
    else:
        pipeline = Pipeline([
            ('svm', SVR(
                C=1.0, 
                epsilon=0.2, 
                gamma='auto',
                kernel='rbf', 
                verbose=True,
                cache_size=3000
                ))
             ])
    
        param_grid = {
            'svm__C': [1.00],#np.arange(0.001, 0.040, 0.010),
            'svm__epsilon': [0.2],#np.arange(500,5000,1000), 
        }

    #run if optimisation is needed
    if do_optimisation:
        optimise(pipeline, X_train, y_train)


    #run the below for regular model training
    # grid search is done on set of parameters (not actually a grid search)
    # the below is done for setting the scoring parameter and setting cross validation
    gs = GridSearchCV(pipeline, param_grid = param_grid, scoring="mean_squared_error", cv=10)
    gs.fit(X_train, y_train)

    print(gs.scorer_)

    import pdb; pdb.set_trace()

    print("Mean squared score for 10 fold cross validation is: ", -gs.best_score_ )
    pipeline = gs

    #save the model that's trained
    if pickle_model:
        import pdb; pdb.set_trace()
        if use_nn:
            file_name = "nn_current_model"
        else:
            file_name = "svm_current_model"
        fileObject = open(file_name,'wb')
        pickle.dump(pipeline, fileObject)
        fileObject.close()
        print("Pickled the model.")


if __name__ == "__main__":
    print("Starting script")
    # execute only if run as a script
    main()
    print("Script finished!")

