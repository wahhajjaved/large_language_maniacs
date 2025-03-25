#-*-coding:utf-8-*-

#这是naruto的应用配置包，包含开发所用的邮箱，数据库的基础配置。还有测试、生产的专业配置等

import os

#当前文件所在路径的规范写法
basedir=os.path.abspath(os.path.dirname(__file__))

#基础包
class Config:
    #给程序创建密匙防止被攻击（具体原理还未搞明白）
    SECRET_KEY=os.environ.get('SECRET_KEY') or os.urandom(16) 
    #可以这么理解，这是在会话teardown后commit数据到数据库
    SQLALCHEMY_COMMIT_ON_TEARDOWN=True
    #这里把数据库迁移回滚设置成True
    SQLALCHEMY_TRACK_MODIFICATIONS=True
    #前缀，mail包里说一般默认是Flasky（还不太明白）|这是自己设置的参数
    FLASKY_MAIL_SUBJECT_PREFIX='老王'
    #这里有两个参数，第一个是user名自己改，第二个是邮箱。（估计只能等测试后才明白是什么东西吧。）
    FLASKY_MAIL_SENDER=os.environ.get('FLASKY_MAIL_SENDER')
    FLASKY_ADMIN=os.environ.get('FLASKY_ADMIN')
    #邮箱服务商
    MAIL_SERVER='smtp.qq.com'
    #腾讯说他家的一般是465或587
    MAIL_PORT=587
    #安全协议
    MAIL_USE_TLS=True
    #发件人账号密码，环境变量中设置
    MAIL_USERNAME=os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD') 
    #定义选染每页的消息数
    FLASKY_POSTS_PER_PAGE=5
    FLASKY_FOLLOWERS_PER_PAGE=5
    FLASKY_COMMENTS_PER_PAGE=5
    SSL_DISABLE=False
    FLASK_SLOW_DB_QUERY_TIME=0.5
    SQLALCHEMY_RECORD_QUERIES=True
    #静态方法可以在不创建类的实例的情况下使用类的方法
    @staticmethod
    def init_app(app):
        pass
        
#开发包
class DevelopmentConfig(Config):
    #开启调试模式后，启动程序后更改源码。程序不会中断，会随之改变。
    DEBUG=True
    #创建数据库接口，或者使用环境变量（提前设置）或者采用显式路径，将来数据库的地址及名称
    SQLALCHEMY_DATABASE_URI=os.environ.get('DEV_DATABASE_URL') or \
        'sqlite:///'+os.path.join(basedir,'data-dev.sqlite')
     
    
#测试包
class TestingConfig(Config):
    #开启测试模式
    TESTING=True
    WTF_CSRF_ENABLED=False
    SQLALCHEMY_DATABASE_URI=os.environ.get('TEST_DATABASE_URL') or \
        'sqlite:///'+os.path.join(basedir,'data-test.sqlite')
        
#生产包
class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL') or \
        'sqlite:///'+os.path.join(basedir,'data.sqlite')
        
    @classmethod
    def init_app(cls,app):
        config.init_app(app)
        
        #错误发送给管理员
        import logging
        from logging.handlers import SMTPHandler
        credentials=None
        secure=None
        if getattr(cls,'MAIL_USERNAME',None)is not None:
            credentials=(cls.MAIL_USERNAME,cls.MAIL_PASSWORD)
            if getattr(cls,'MAIL_USE_TLS',None):
                secure=()
        mail_handler=STMPHandler(
                                    mailhost=(cls.MAIL_SERVER,cls.MAIL_PORT),
                                    fromaddr=cls.FLASKY_MAIL_SENDER,
                                    toaddr=[cls.FLASKY_ADMIN],
                                    subject=cls.FLASKY_MAIL_SUBJECT_PREFIX+'Application Error',
                                    credentials=credentials,
                                    secure=secure
                                    )
        mail_handler.setlevel(logging.ERROR)
        app.logger.addHandler(mail_handler)

class HerokuConfig(ProductionConfig):
    SSL_DISABLE=bool(os.environ.get('SSL_DISABLE'))

    @classmethod
    def init_app(cls,app):
        ProductionConfig.init_app(app)
        
        from werkzeug.contrib.fixers import ProxyFix
        app.wsgi_app=ProxyFix(app.wsgi_app)
        
        #输出到stderr
        import logging
        from logging import StreamHandler
        file_handler=StreamHandler()
        file_handler.setlevel(logging.WARNING)
        app.logger.addHandler(file_handler)
        
#包的字典
config={
    'development':DevelopmentConfig,
    'testing':TestingConfig,
    'production':ProductionConfig,
    'heroku': HerokuConfig,
    'default':DevelopmentConfig
}















        
    
