import numpy


predictions = []
true_scores = []
nb_of_generations = -1
nb_of_directions = -1
filenameDIR = -1
filenameSCORE = -1
score_towrite_tab = []

def computeQualityEvaluation():
    global predictions, true_scores, nb_of_generations, nb_of_directions

    towrite = []
    towriteSTAR = []

    for g in range(nb_of_generations):
        nb_off_predict_star = 0
        sum_mse_star = 0.0
        sum_mae_star = 0.0
        sum_tcheby_pred_star = 0.0
        sum_tcheby_free_star = 0.0
        for d in range(nb_of_directions):
            sum_tcheby_pred = 0.0
            sum_tcheby_free = 0.0
            sum_mse = 0.0
            sum_mae = 0.0
            nb_off_predict_for_d = len(predictions[g][d])
            #print(g,d, nb_off_predict_for_d)
            nb_off_predict_star += nb_off_predict_for_d
            for o in range(nb_off_predict_for_d):
                tmp_mse       = (predictions[g][d][o] - true_scores[g][d][o])**2
                sum_mse      += tmp_mse
                sum_mse_star += tmp_mse

                tmp_mae       = abs(predictions[g][d][o] - true_scores[g][d][o])
                sum_mae      += tmp_mae
                sum_mae_star += tmp_mae

                sum_tcheby_pred += predictions[g][d][o]
                sum_tcheby_free += true_scores[g][d][o]

            sum_tcheby_pred_star += sum_tcheby_pred
            sum_tcheby_free_star += sum_tcheby_free
            towrite.append(str(g))
            towrite.append( ' ' )
            towrite.append(str(d))
            towrite.append( ' ' )
            towrite.append( str(sum_mse / nb_off_predict_for_d) )
            towrite.append( ' ' )
            towrite.append( str(sum_mae / nb_off_predict_for_d) )
            towrite.append( ' ' )
            towrite.append( str(sum_tcheby_pred / nb_off_predict_for_d) )
            towrite.append( ' ' )
            towrite.append( str(sum_tcheby_free / nb_off_predict_for_d) )
            towrite.append( '\n' )
        towriteSTAR.append(str(g))
        towriteSTAR.append(' ')
        towriteSTAR.append("*")
        towriteSTAR.append(' ')
        towriteSTAR.append( str(sum_mse_star / nb_off_predict_star) )
        towriteSTAR.append(' ')
        towriteSTAR.append( str(sum_mae_star / nb_off_predict_star) )
        towriteSTAR.append( ' ' )
        towriteSTAR.append( str(sum_tcheby_pred_star / nb_off_predict_star) )
        towriteSTAR.append( ' ' )
        towriteSTAR.append( str(sum_tcheby_free_star / nb_off_predict_star) )
        towriteSTAR.append( '\n' )


    fd = open(filenameDIR, 'a')
    fd.write(''.join(towrite))
    fd.close()
    filenameDIRSTAR = filenameDIR.replace("DIR_UF", "DIRSTAR_UF")
    fd = open(filenameDIRSTAR, 'a')
    fd.write(''.join(towriteSTAR))
    fd.close()

def resetGlobalVariables(filenameD, filenameS , nb_g, nb_d):
    global predictions, true_scores, filenameDIR, nb_of_generations, nb_of_directions, filenameSCORE
    filenameSCORE = filenameS
    score_towrite_tab = []
    filenameDIR = filenameD
    predictions = []
    true_scores = []
    nb_of_directions = nb_d
    nb_of_generations = nb_g
    for g in range(nb_of_generations):
        predictions.append([])
        true_scores.append([])
        for d in range(nb_of_directions):
            predictions[g].append([])
            true_scores[g].append([])

def generateDiffPredFreeFile():
    global filenameSCORE, score_towrite_tab
    fd = open(filenameSCORE, 'a')
    fd.write(''.join(score_towrite_tab))
    fd.close()

def addToScoreTab(current_g, current_f, score_best_pred, save_best_pred_free_score, index_best_pred, score_best_free, save_best_free_pred_score,  index_best_free):
    score_towrite_tab.append(str(current_g))
    score_towrite_tab.append(' ')
    score_towrite_tab.append(str(current_f))
    score_towrite_tab.append(' ')
    score_towrite_tab.append(str(score_best_pred))
    score_towrite_tab.append(' ')
    score_towrite_tab.append(str(save_best_pred_free_score))
    score_towrite_tab.append(' ')
    score_towrite_tab.append(str(save_best_free_pred_score))
    score_towrite_tab.append(' ')
    score_towrite_tab.append(str(score_best_free))
    score_towrite_tab.append(' ')
    score_towrite_tab.append('1' if index_best_pred == index_best_free else '0')
    score_towrite_tab.append('\n')

def add(generation, direction, predict_score, true_score_oldzstar):
    predictions[generation][direction].append(predict_score)
    true_scores[generation][direction].append(true_score_oldzstar)
