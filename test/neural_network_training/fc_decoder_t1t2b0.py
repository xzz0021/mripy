"""
function simulate MRF and perform the training of cnn model
"""

from joblib import Parallel, delayed
import multiprocessing
import bloch_sim.sim_seq_array_data as ssad
import bloch_sim.sim_spin as ss
import numpy as np
import bloch_sim.sim_seq as sseq
import scipy.io as sio
import tensorflow as tf
import bloch_sim.sim_seq_MRF_irssfp_cuda as ssmrf
pathdat = '/working/larson/UTE_GRE_shuffling_recon/MRF/sim_ssfp_fa10_t1t2/IR_ssfp_t1t2b0pd5/'
pathexe = '/home/pcao/git/mripy/test/neural_network_training/'
    
def test():
    import tensorflow as tf
    sess = tf.InteractiveSession()    

    #define x and y_
    x = tf.placeholder(tf.float32, shape=[None, 4]) #changed 784 to 1000
    y_ = tf.placeholder(tf.float32, shape=[None, 2*960])    

    def weight_variable(shape):
      initial = tf.truncated_normal(shape, stddev=0.1)
      return tf.Variable(initial)    

    def bias_variable(shape):
      initial = tf.constant(0.1, shape=shape)
      return tf.Variable(initial)    

    #define convolution and max pooling
    def conv2d(x, W):
      return tf.nn.conv2d(x, W, strides=[1, 1, 1, 1], padding='SAME')    

    def max_pool_2x2(x):
      return tf.nn.max_pool(x, ksize=[1, 2, 1, 1],
                            strides=[1, 2, 1, 1], padding='SAME')    
    

    #############dense connection layer 1
    #weighting and bias for a layer with 1024 neurons
    W_fc1 = weight_variable([4, 2048])  #40*48 *64 /32
    b_fc1 = bias_variable([2048])    

    # densely connected layer with relu output
    h_pool2_flat = tf.reshape(x, [-1, 4])
    h_fc1 = tf.nn.relu(tf.matmul(h_pool2_flat, W_fc1) + b_fc1)    
    
    

    #############dense connection layer 2
    #weighting and bias for a layer with 1024 neurons
    W_fc2 = weight_variable([2048, 2048])  #40*48 *64 /32
    b_fc2 = bias_variable([2048])    

    # densely connected layer with relu output
    h_fc2 = tf.sigmoid(tf.matmul(h_fc1, W_fc2) + b_fc2)    
    

    #############dense connection layer 3
    #weighting and bias for a layer with 1024 neurons
    #W_fc3 = weight_variable([1024, 1024])  #40*48 *64 /32
    #b_fc3 = bias_variable([1024])    

    # densely connected layer with relu output
    #h_fc3 = tf.nn.relu(tf.matmul(h_fc2, W_fc3) + b_fc3)    

    #############last layer with dropout
    #do dropout for the last layer, densely connected
    keep_prob = tf.placeholder(tf.float32)
    h_fcn_drop = tf.nn.dropout(h_fc2, keep_prob)    

    W_fcn = weight_variable([2048, 1920])
    b_fcn = bias_variable([1920])    

    #fully connected layer; changed tf.argmax to tf.sigmoid, could also try tf.tanh and tf.nn.relu (not work)
    y_conv = (tf.matmul(h_fcn_drop, W_fcn) + b_fcn)    
    

    #changed AdamOptimizer(1e-4) to GradientDescentOptimizer(0.05)
    # l2-norm
    loss = tf.reduce_sum(tf.pow(tf.subtract(y_conv, (y_)),2))    

    #sigmoid_cross_entropy_with_logits
    #loss = tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits((y_conv), (y_)))    

    #algrithm
    train_step = tf.train.AdamOptimizer(1e-4).minimize(loss)    

    #training accuracy
    correct_prediction = tf.pow(tf.subtract(y_conv, (y_)),2)
    accuracy = tf.reduce_mean(correct_prediction)    

    #intial sess
    sess.run(tf.global_variables_initializer())    

    #define batch size and mini batch size
    batch_size = 800    

    # load far and trr
    # read rf and tr arrays from mat file
    mat_contents  = sio.loadmat(pathdat+'mrf_rf_tr.mat');
    far           = np.array(mat_contents["rf"].astype(np.complex128).squeeze())
    trr           = np.array(mat_contents["trr"].astype(np.float64).squeeze())
    # prepare for sequence simulation, y->x_hat
    Nk            = far.shape[0]
    ti            = 10 #ms
    M0            = np.array([0.0,0.0,1.0]).astype(np.float64) 

    #run tensorflow on cpu, count of gpu = 0
    config = tf.ConfigProto()#(device_count = {'GPU': 0})
    #allow tensorflow release gpu memory
    config.gpu_options.allow_growth=True  

    #run for 2000
    for i in range(200000):
        batch_ys = np.random.uniform(0,1,(batch_size,4)).astype(np.float64)
        batch_xs = np.zeros((batch_size,2*Nk), dtype = np.float64)
        # intial seq simulation with t1t2b0 values
        #seq_data = ssad.irssfp_arrayin_data( batch_size, Nk ).set( batch_ys )    
        T1r, T2r, dfr, PDr = ssmrf.set_par(batch_ys)
        batch_xs_c         = ssmrf.bloch_sim_batch_cuda( batch_size, 100, Nk, PDr,\
         T1r, T2r, dfr, M0, trr, far, ti )

        # intial seq simulation with t1t2b0 values
        #seq_data = ssad.irssfp_arrayin_data( batch_size, Nk ).set( batch_ys )    

        #inputs = range(batch_size)
        #def processFunc(i):
        #    S = seq_data.sim_seq_tc(i,M0, trr, far, ti )
        #    return S    

        #num_cores = multiprocessing.cpu_count()
        #batch_xs_c = Parallel(n_jobs=16, verbose=5)(delayed(processFunc)(i) for i in inputs)    

        #add noise
        #rand_c = np.random.uniform(-0.001,0.001,(batch_size,Nk)) + 1j*np.random.uniform(-0.001,0.001,(batch_size,Nk))    

        #batch_xs_c = batch_xs_c + rand_c
        #seperate real/imag parts or abs/angle parts, no noise output
        batch_xs[:,0:Nk] = np.real(batch_xs_c)
        batch_xs[:,Nk:2*Nk] = np.imag(batch_xs_c)    
        #input with noise
        batch_xsnoise = batch_xs + np.random.uniform(-0.01,0.01,(batch_size,2*Nk))    

        #input with noise
        #batch_xsnoise = batch_xs + np.random.uniform(-0.001,0.001,(batch_size,2*Nk))    

        train_step.run(feed_dict={x: batch_ys, y_: batch_xs, keep_prob: 0.5})
        if i%1000 == 0:
            train_error = accuracy.eval(feed_dict={x: batch_ys, y_: batch_xs, keep_prob: 1.0})
            print("step %d, training error %g"%(i, train_error))
        if i%1000 == 0:
            #save the model into file
            saver = tf.train.Saver()
            saver.save(sess,pathexe + 'check_point/fc_dencoder_t1t2b0-mrf-ir-ssfp-noise0p01-20170507')    
    

    #save the model into file
    saver = tf.train.Saver()
    saver.save(sess,pathexe + 'check_point/fc_dencoder_t1t2b0-mrf-ir-ssfp-noise0p01-20170507')    
