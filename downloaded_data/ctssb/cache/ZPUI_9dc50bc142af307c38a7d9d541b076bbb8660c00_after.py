from time import sleep

def Printer(message, i, o, sleep_time=1, skippable=True):
    """Outputs string data on display as soon as it's called.                                          
                                                                               
    Args:                                                                    
                                                                             
        * ``message``: A string or list of strings to display. A string will be split into a list, a list will not be modified. The resulting list is then displayed string-by-string.
        * ``i``, ``o``: input&output device objects. If you're not using skippable=True and don't need exit on KEY_LEFT, feel free to pass None as i.
                                                                             
    Kwargs:                                                                  
                                                                                 
        * ``sleep_time``: Time to display each the message (for each of resulting screens).
        * ``skippable``: If set, allows skipping message screens by presing ENTER.
                                                                                 
    """                                                                      
    Printer.skip_screen_flag = False #A flag which is set for skipping screens and is polled while printer is displaying things
    Printer.exit_flag = False #A flag which is set for stopping exiting the printing process completely

    #I need to make it this function's attribute because this is a nonlocal variable and AFAIK the only neat way to change it reliably
    def skip_screen():
        Printer.skip_screen_flag = True

    def exit_printer():
        Printer.exit_flag = True

    #If skippable option is enabled, etting input callbacks on keys we use for skipping screens
    if i is not None: #Can be on boot or whenever
        i.stop_listen()
        i.clear_keymap()
        if skippable:
            i.set_callback("KEY_KPENTER", skip_screen)
            i.set_callback("KEY_ENTER", skip_screen)
        i.set_callback("KEY_LEFT", exit_printer)
        i.listen()

    #Now onto rendering the message
    rendered_message = []
    if type(message) in (str, unicode): #Dividing the string into screen-sized chunks
        screen_width = o.cols
        while message:
           rendered_message.append(message[:screen_width])
           message = message[screen_width:]
    elif type(message) == list: #It's simple then, just output it as it is.
       rendered_message = message

    #Now onto calculating the parameters and displaying the message screen-by-screen
    screen_rows = o.rows
    render_length = len(rendered_message)
    num_screens = render_length/screen_rows #Number of screens it will take to show the whole message
    if render_length%screen_rows != 0: #There is one more screen necessary, it's just not full but we need it.
        num_screens += 1
    for screen_num in range(num_screens):
        Printer.skip_screen_flag = False
        shown_element_numbers = [(screen_num*screen_rows)+i for i in range(screen_rows)]
        screen_data = [rendered_message[i] for i in shown_element_numbers if i in range(render_length)] 
        o.display_data(*screen_data)
        if skippable:
            poll_period = 0.1
            sleep_periods = sleep_time/poll_period
            for period in range(int(sleep_periods)):
                if Printer.exit_flag:
                    return #Exiting the function completely
                if Printer.skip_screen_flag:
                     break #Going straight to the next screen
                sleep(poll_period)
        else:
            if Printer.exit_flag:
                return
            sleep(sleep_time)
