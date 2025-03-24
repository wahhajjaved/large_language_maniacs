#build a spark cluster
#needs some refactoring but works fine for now
#other handy things
# sudo yum --enablerepo epel-testing install s3cmd

import json

def get_pars(spark_file="../myspark.json"):
    JSONDC=json.JSONDecoder()
    p=JSONDC.decode(open(spark_file,'rU').read())
    return p

def stop_spark(p):
    print 'stopping'
    cmd="spark-ec2 -k %s -i ~/%s.pem -r %s stop %s"%(p['pem'],p['pem'],p['region'],p['name'])
    cmd=p['ec2_dir']+'/'+cmd
    run_in_shell(cmd)

def destroy_spark(p):
    print 'destroy'
    cmd="spark-ec2 -k %s -i ~/%s.pem -r %s destroy %s"%(p['pem'],p['pem'],p['region'],p['name'])
    cmd=p['ec2_dir']+'/'+cmd
    run_in_shell(cmd)


def start_spark(p):
    print 'starting'
    cmd="spark-ec2 -k %s -i ~%s/.pem -r %s start %s"%(p['pem'],p['pem'],p['region'],p['name'])
    cmd=p['ec2_dir']+'/'+cmd
    run_in_shell(cmd)

def launch_spark(p):
    cmd="spark-ec2 -k %s -i ~/%s.pem -r %s"%(p['pem'],p['pem'],p['region'])
    cmd=cmd+" -u %s -s %s -t %s"%(p['user'],p['n_slaves'],p['type'])
    cmd=cmd+" --ebs-vol-size %s -w %s"%(p['diskGB'],p['wait'])
    print p['spot_price'].__class__
    if p['spot_price'].__class__ in [int,float]:
        print "Trying for spot price %s on %s in region %s"%(p['spot_price'],p['type'],p['region'])
        spot=float(p['spot_price'])
        if spot > 0 and spot < 1.0:
            cmd=cmd+" --spot-price %s"%spot
        else:
            raise(ValueError,"spot price must be between 0 and 1 or a string")
    else:
        print "not using spot price, not a number"
        pass
             
    cmd=cmd +" launch %s"%p['name']
    cmd=p['ec2_dir']+'/'+cmd
    print "command is:"
    print cmd
    run_in_shell(cmd)

def run_in_shell(cmd):
    import os
    full_cmd="source ~/creds.sh ; %s"%cmd
    os.system(full_cmd)

if __name__ == "__main__":
    #could use some cleaning up
    import sys
    args=sys.argv
    if len(args) == 1:
        p=get_pars()
        launch_spark(p)
    elif len(args) == 2:
        spark_file=sys.args[1] 
        p=get_pars(spark_file)
        launch_spark(p)
    elif len(args) == 3:
        if args[2] not in ['stop','start','destroy']: raise(ValueError,"I only know start and stop for second arg")
        spark_file=sys.argv[1]
        p=get_pars(spark_file)
        if args[2] == 'start': start_spark(p)
        if args[2] == 'stop': stop_spark(p)
        if args[2] == 'destroy': destroy_spark(p)
