# Import convention
import streamlit as st

# 출력 메서드
st.text('Tushar-Aggarwal.com') # 화면에 출력 또는 입력을 받으려면 st.어쩌구()를 거쳐야 합니다.
st.markdown('[Tushar-Aggarwal.com](https://tushar-aggarwal.com)')
st.caption('Success')
st.latex(r''' e^{i\pi} + 1 = 0 ''') # 수식을 출력하는 문법 
st.write('Supreme Applcations by Tushar Aggarwal') # 알아서 안에 있는 내용을 변환 
st.write(['st', 'is <', 3]) # see *
st.title('Streamlit Magic Cheat Sheets')
st.header('Developed by Tushar Aggarwal')
st.subheader('visit tushar-aggarwal.com')
st.code('for i in range(8): print(i)')
st.image('https://i.imgur.com/MDKQoDc.jpg', width=300)

# * optional kwarg unsafe_allow_html = True
hello = 1
# streamlit run 파일명.py
st.title('hello')


# 입력
st.button('Demo')

import pandas as pd

df=pd.DataFrame({'key':[1,2,3]})

st.data_editor(df)
st.checkbox('Option 1') # 여러문항 중 여러개 선택(중복) / True, False
# 여러개 중 단일 항목 선택
st.radio('Pick Country:', ['France','Germany'])
# 여러개 중 단일 항목 선택
st.selectbox('Select', [1,2,3])
# 여러개 중 중복 항목 선택
st.multiselect('Multiselect', [1,2,3])
st.slider('Slide me', min_value=0, max_value=10)
st.select_slider('Slide to select', options=[1,'2', 3])
st.text_input('Enter Article')
st.number_input('Enter required number')
# 긴 문자열을 받을 때 
st.text_area('Entered article text')
st.date_input('Select date')
st.time_input('Select Time')
st.file_uploader('File CSV uploader')

data = st.camera_input('Click a Snap')

if data: # data 변수에 값이 있으면 아래 부분이 동작
    st.download_button(
        label="Download image",
        data=data,
        file_name="my_picture.png",
        mime="image/png",
    )

st.color_picker('Pick a color')