import os
import sys
import torch
import torch.autograd as autograd
import torch.nn.functional as F


def train(train_iter, dev_iter, model, args):
    if args.cuda:
        model.cuda()

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    steps = 0
    model.train()
    for epoch in range(1, args.epochs+1):
        for batch in train_iter:
            feature, target = batch.text, batch.label
            feature.data.t_(), target.data.sub_(1)  # batch first, index align
            if args.cuda:
                feature, target = feature.cuda(), target.cuda()

            optimizer.zero_grad()
            logit = model(feature)
            loss = F.cross_entropy(logit, target)
            loss.backward()
            optimizer.step()

            steps += 1
            if steps % args.log_interval == 0:
                corrects = (torch.max(logit, 1)[1].view(target.size()).data == target.data).sum()
                accuracy = corrects/batch.batch_size * 100.0
                sys.stdout.write(
                    '\rBatch[{}] - loss: {:.6f}  acc: {:.4f}%({}/{})'.format(steps, 
                                                                             loss.data[0], 
                                                                             accuracy,
                                                                             corrects,
                                                                             batch.batch_size))
            if steps % args.test_interval == 0:
                eval(dev_iter, model, args)
            if steps % args.save_interval == 0:
                if not os.path.isdir(args.save_dir): os.makedirs(args.save_dir)
                save_prefix = os.path.join(args.save_dir, 'snapshot')
                save_path = '{}_steps{}.pt'.format(save_prefix, steps)
                torch.save(model, save_path)


def eval(data_iter, model, args):
    model.eval()
    corrects, avg_loss = 0, 0
    for batch in data_iter:
        feature, target = batch.text, batch.label
        feature.data.t_(), target.data.sub_(1)  # batch first, index align
        if args.cuda:
            feature, target = feature.cuda(), target.cuda()

        logit = model(feature)
        loss = F.cross_entropy(logit, target, size_average=False)

        avg_loss += loss.data[0]
        corrects += (torch.max(logit, 1)
                     [1].view(target.size()).data == target.data).sum()

    size = len(data_iter.dataset)
    avg_loss = loss.data[0]/size
    accuracy = corrects/size * 100.0
    model.train()
    print('\nEvaluation - loss: {:.6f}  acc: {:.4f}%({}/{}) \n'.format(avg_loss, 
                                                                       accuracy, 
                                                                       corrects, 
                                                                       size))
    return accuracy

def predict(text, model, text_field, label_feild):
    assert isinstance(text, str)
    model.eval()
    text = text_field.tokenize(text)
    text = text_field.preprocess(text)
    text = [[text_field.vocab.stoi[x] for x in text]]
    x = text_field.tensor_type(text)
    x = autograd.Variable(x, volatile=True)
    print(x)
    output = model(x)
    _, predicted = torch.max(output, 1)
    return label_feild.vocab.itos[predicted.data[0][0]+1]

def train_logistic(char_train_data, char_dev_data, word_train_data, word_dev_data, char_model, word_model, logistic_model, args):
    if args.cuda:
        logistic_model.cuda()
    optimizer = torch.optim.Adam(logistic_model.parameters(), lr=args.lr)

    steps = 0
    logistic_model.train()
    for epoch in range(1, args.epochs+1):
        for char_batch, word_batch in zip(char_train_data,word_train_data):
            # word_batch = next(word_train_data)

            char_feature, char_target = char_batch.text, char_batch.label
            char_feature.data.t_(), char_target.data.sub_(1)  # batch first, index align
            char_feature.volatile = True

            word_feature, word_target = word_batch.text, word_batch.label
            word_feature.data.t_(), word_target.data.sub_(1)  # batch first, index align
            word_feature.volatile = True
            # print(char_batch.data, word_batch.data)
            if args.cuda:
                char_feature, char_target = char_feature.cuda(), char_target.cuda()
                word_feature, word_target = word_feature.cuda(), word_target.cuda()

            assert char_target.data[0] == word_target.data[0], "Mismatching data sample! {}, {}".format(char_target.data,
                                                                                                        word_target.data)

            char_output = char_model(char_feature)
            word_output = word_model(word_feature)

            char_output.volatile = False
            word_output.volatile = False
            char_feature.volatile = False
            word_feature.volatile = False

            optimizer.zero_grad()
            logit = logistic_model(char_output, word_output)
            loss = F.cross_entropy(logit, char_target)
            loss.backward()
            optimizer.step()

            steps += 1
            if steps % args.log_interval == 0:
                corrects = (torch.max(logit, 1)[1].view(char_target.size()).data == char_target.data).sum()
                accuracy = corrects/char_batch.batch_size * 100.0
                sys.stdout.write(
                    '\rBatch[{}] - loss: {:.6f}  acc: {:.4f}%({}/{})'.format(steps,
                                                                             loss.data[0],
                                                                             accuracy,
                                                                             corrects,
                                                                             char_batch.batch_size))
            if steps % args.test_interval == 0:
                eval_logistic(char_dev_data, word_dev_data,char_model, word_model, logistic_model, args)
            # if steps % args.save_interval == 0:
            #     if not os.path.isdir(args.save_dir): os.makedirs(args.save_dir)
            #     save_prefix = os.path.join(args.save_dir, 'snapshot')
            #     save_path = '{}_steps{}.pt'.format(save_prefix, steps)
            #     torch.save(logistic_model, save_path)

def eval_logistic(char_data, word_data, char_model, word_model, logistic_model, args):
    logistic_model.eval()
    corrects, avg_loss = 0, 0
    for char_batch, word_batch in zip(char_data, word_data):
        char_feature, char_target = char_batch.text, char_batch.label
        char_feature.data.t_(), char_target.data.sub_(1)  # batch first, index align
        char_feature.volatile = True

        word_feature, word_target = word_batch.text, word_batch.label
        word_feature.data.t_(), word_target.data.sub_(1)  # batch first, index align
        word_feature.volatile = True

        if args.cuda:
            char_feature, char_target = char_feature.cuda(), char_target.cuda()
            word_feature, word_target = word_feature.cuda(), word_target.cuda()

        assert char_target.data[0] == word_target.data[0], "Mismatching data sample! {}, {}".format(char_target, word_target)

        char_output = char_model(char_feature)
        word_output = word_model(word_feature)


        logit = logistic_model(char_output, word_output)
        loss = F.cross_entropy(logit, char_target, size_average=False)

        char_feature.volatile = False
        word_feature.volatile = False

        avg_loss += loss.data[0]
        corrects += (torch.max(logit, 1)
                     [1].view(char_target.size()).data == char_target.data).sum()

    size = len(char_data.data())
    avg_loss = loss.data[0] / size
    accuracy = corrects / size * 100.0
    logistic_model.train()
    print('\nEvaluation - loss: {:.6f}  acc: {:.4f}%({}/{}) \n'.format(avg_loss,
                                                                       accuracy,
                                                                       corrects,
                                                                       size))
    return accuracy