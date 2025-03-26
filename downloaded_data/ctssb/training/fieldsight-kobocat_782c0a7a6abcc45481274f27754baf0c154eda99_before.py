import json
from io import BytesIO
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.platypus import Spacer, SimpleDocTemplate, Table, TableStyle, PageBreak
from reportlab.platypus import Image
from reportlab.lib import colors
from onadata.apps.fsforms.reports_util import get_instaces_for_site_individual_form
from django.db.models import Prefetch
from onadata.apps.fsforms.models import FieldSightXF, FInstance, Site
styleSheet = getSampleStyleSheet()
 
class MyPrint:


    def __init__(self, buffer, pagesize):
        self.main_answer = {}
        self.question={}
        self.data=[]
        self.buffer = buffer
        if pagesize == 'A4':
            self.pagesize = A4
        elif pagesize == 'Letter':
            self.pagesize = letter
        self.width, self.height = self.pagesize
        self.base_url = ''
        self.media_folder = ''
    @staticmethod
    def _header_footer(canvas, doc):
        # Save the state of our canvas so we can draw on it
        canvas.saveState()
        styles = getSampleStyleSheet()
 
        # Header
        header = Paragraph('Fieldsight', styles['Normal'])
        w, h = header.wrap(doc.width, doc.topMargin)
        header.drawOn(canvas, doc.leftMargin, doc.height + doc.topMargin)
 
        # Footer
        footer = Paragraph('Naxalicious  ' * 5, styles['Normal'])
        w, h = footer.wrap(doc.width, doc.bottomMargin)
        footer.drawOn(canvas, doc.leftMargin, h)
 
        # Release the canvas
        canvas.restoreState()
    def create_logo(self, absolute_path):
        image = Image(absolute_path)
        image._restrictSize(3 * inch, 3 * inch) 
        return image
    def parse_repeat(self, r_object):
        styNormal = styleSheet['Normal']
        styBackground = ParagraphStyle('background', parent=styNormal, backColor=colors.white)
        gnr_question = r_object['name']
        for gnr_answer in self.main_answer[gnr_question]:
            for first_children in r_object['children']:
                question = first_children['name']
                group_answer = self.main_answer[gnr_question]
                question_label = first_children['label']
                if gnr_question+"/"+question in gnr_answer:
                    if first_children['type'] == 'note':
                        answer= '' 
                    elif first_children['type'] == 'photo':
                        #photo = '/media/user/attachments/'+ gnr_answer[gnr_question+"/"+question]
                        photo = 'http://'+self.base_url+'/media/'+self.media_folder+'/attachments/'+ gnr_answer[gnr_question+"/"+question]
                        answer = self.create_logo(photo)
                        # answer =''
                    else:
                        answer = gnr_answer[gnr_question+"/"+question]
                else:
                    answer = ''
                if 'label' in first_children:
                    question = first_children['label']
                row=[Paragraph(question, styBackground), answer]
                self.data.append(row)

    def parse_group(self, g_object):
        styNormal = styleSheet['Normal']
        styBackground = ParagraphStyle('background', parent=styNormal, backColor=colors.white)
        gnr_question = g_object['name']
        for first_children in g_object['children']:
            question = first_children['name']
            if gnr_question+"/"+question in self.main_answer:
                if first_children['type'] == 'note':
                    answer= '' 
                elif first_children['type'] == 'photo':
                    photo = 'http://'+self.base_url+'/media/'+self.media_folder+'/attachments/'+self.main_answer[gnr_question+"/"+question]
                    answer = self.create_logo(photo)
                else:
                    answer = self.main_answer[gnr_question+"/"+question]
            else:
                answer = ''
            if 'label' in first_children:
                question = first_children['label']
            row=[Paragraph(question, styBackground), answer]
            self.data.append(row)

    def parse_individual_questions(self, parent_object):
        styNormal = styleSheet['Normal']
        styBackground = ParagraphStyle('background', parent=styNormal, backColor=colors.white)
        answer=self.main_answer
        for first_children in parent_object:
            if first_children['type'] == "repeat":
                self.parse_repeat(first_children)
            elif first_children['type'] == 'group':
                self.parse_group(first_children)
            else:
                question = first_children['name']

                if first_children['type'] == 'note' or question not in self.main_answer:
                    answer= Paragraph('', styBackground) 

                elif first_children['type'] == 'photo':
                    photo = 'http://'+self.base_url+'/media/'+self.media_folder+'/attachments/'+self.main_answer[question]
                    answer = self.create_logo(photo)
                else:
                    answer = Paragraph(self.main_answer[question], styBackground)
                
                if 'label' in first_children:
                    question = first_children['label']
                row=(Paragraph(question, styBackground), answer)
                self.data.append(row)


    def print_users(self, pk, base_url):
        self.base_url = base_url
        buffer = self.buffer
        doc = SimpleDocTemplate(buffer,
                                rightMargin=72,
                                leftMargin=72,
                                topMargin=72,
                                bottomMargin=72,
                                pagesize=self.pagesize)
 
        # Our container for 'Flowable' objects
        elements = []
        
        # A large collection of style sheets pre-made for us
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='centered', alignment=TA_CENTER))
        site = Site.objects.get(pk=pk)
        elements.append(Paragraph(site.name, styles['Heading1']))
        elements.append(Paragraph(site.identifier, styles['Normal']))
        elements.append(Paragraph(site.address, styles['Normal']))
        elements.append(Paragraph(site.phone, styles['Normal']))
        if site.region:
            elements.append(Paragraph(site.region.name, styles['Normal']))
        elements.append(Spacer(0,10))
        elements.append(Spacer(0,10))
        elements.append(Paragraph('Responses', styles['Heading2']))
        elements.append(Spacer(0,10))
        
        forms = FieldSightXF.objects.select_related('xf').filter(site_id=pk, is_survey=False).prefetch_related(Prefetch('site_form_instances', queryset=FInstance.objects.select_related('instance'))).order_by('-is_staged', 'is_scheduled')
        #a=FieldSightXF.objects.select_related('xf').filter(site_id=291).prefetch_related(Prefetch('site_form_instances', queryset=FInstance.objects.select_related('instance')))

       
        
        ts1 = TableStyle([
                ('ALIGN', (0,0), (-1,0), 'RIGHT'),
                ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('GRID', (0,0), (-1,-1), 0.25, colors.black),
                    ])
        styNormal = styleSheet['Normal']
        styBackground = ParagraphStyle('background', parent=styNormal, backColor=colors.white)

        for form in forms:
            elements.append(Spacer(0,10))
            elements.append(Paragraph(form.xf.title, styles['Heading3']))
            elements.append(Paragraph(form.form_type(), styles['Heading4']))
            if form.is_staged:
                if form.stage.stage:
                    elements.append(Paragraph("Stage: " + str(form.stage.stage.project_stage_id), styles['Heading5']))
                    elements.append(Paragraph("Sub Stage: " + str(form.stage.project_stage_id), styles['Heading5']))    
                else:
                    elements.append(Paragraph("Stage: " + str(form.stage.project_stage_id), styles['Heading5']))

                elements.append(Paragraph(form.form_type(), styles['Heading4']))
            json_question = form.xf.json
            form_user_name = form.xf.user.username
            self.media_folder = form_user_name

            #cursor = get_instaces_for_site_individual_form(form.id)
            
            
            sub_count = 0
            if form.site_form_instances.all():
                for instance in form.site_form_instances.all():
                    sub_count += 1
                    elements.append(Spacer(0,10))
                    elements.append(Paragraph("Submision "+ str(sub_count), styles['Heading4']))
                    elements.append(Paragraph("Submitted By:"+instance.submitted_by.username, styles['Normal']))
                    elements.append(Paragraph("Submitted Date:"+str(instance.date), styles['Normal']))
                    elements.append(Spacer(0,10))
                    self.data = []
                    self.main_answer = instance.instance.json
                    question = json.loads(json_question)
                    self.parse_individual_questions(question['children'])
                    

                    t1 = Table(self.data, colWidths=(60*mm, None))
                    t1.setStyle(ts1)
                    elements.append(t1)
                    elements.append(Spacer(0,10))
            else:
                elements.append(Paragraph("No Submisions Yet. ", styles['Heading5']))
            elements.append(PageBreak())
        #     else:
        #         elements.append(Paragraph("No Submissions Yet.", styles['Normal']))
        #         elements.append(Spacer(0,10)) 
        # else:
        #     elements.append(Paragraph("No Forms Yet.", styles['Normal']))
        #     elements.append(Spacer(0,10)) 
        


            # self.parse_individual_questions(json_question['children'])









     
        doc.build(elements, onFirstPage=self._header_footer, onLaterPages=self._header_footer,
                  canvasmaker=NumberedCanvas)
 
        # Get the value of the BytesIO buffer and write it to the response.
        #pdf = buffer.getvalue()
        #buffer.close()
        #return pdf

    '''
        Usage with django
    @staff_member_required
    def print_users(request):
        # Create the HttpResponse object with the appropriate PDF headers.
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="My Users.pdf"'
     
        buffer = BytesIO()
     
        report = MyPrint(buffer, 'Letter')
        pdf = report.print_users()
     
        response.write(pdf)
        return response
    '''


class NumberedCanvas(canvas.Canvas):


    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []
 

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()
 

    def save(self):
        """add page info to each page (page x of y)"""
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)
 
 
    def draw_page_number(self, page_count):
        # Change the position of this to wherever you want the page number to be
        self.drawRightString(211 * mm, 15 * mm + (0.2 * inch),
                             "Page %d of %d" % (self._pageNumber, page_count))




# if __name__ == '__main__':
#     buffer = BytesIO()
     
#     report = MyPrint(buffer, 'Letter')
#     pdf = report.print_users()
#     buffer.seek(0)
 
#     with open('arquivo.pdf', 'wb') as f:
#         f.write(buffer.read())

# def site_responses_report(data):
#     buffer = BytesIO()
     
#     report = MyPrint(buffer, 'Letter')
#     pdf = report.print_users(data)
#     buffer.seek(0)
 
#     with open('arquivo.pdf', 'wb') as f:
#         f.write(buffer.read())    
