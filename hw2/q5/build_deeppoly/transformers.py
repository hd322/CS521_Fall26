import torch
from constraintflow.lib.polyexp import PolyExpSparse
from constraintflow.lib.symexp import *
from constraintflow.gbcsr.sparse_tensor import SparseTensor
from constraintflow.lib.llist import Llist
from constraintflow.gbcsr.tensor_ops import *
class deeppoly:
	def Affine(self, abs_elem, prev, curr, poly_size, curr_size, prev_size, input_size, batch_size):
		cse_var_21 = prev.dot(curr.get_metadata('weight', batch_size), abs_elem.get_poly_size())
		cse_var_20 = curr.get_metadata('bias', batch_size)
		cse_var_64 = cse_var_21.get_mat(abs_elem)
		cse_var_41 = PolyExpSparse(abs_elem.network, cse_var_64 , binary(cse_var_21.get_const(), cse_var_20, operator.add))
		cse_var_102 = binary(get_dims(cse_var_64), 1, operator.sub)
		cse_var_10 = SparseTensor([], [], 0, torch.tensor([]), dense_const=0.0, type= type(0.0)).unsqueeze(0).unsqueeze(1).unsqueeze(2).repeat(torch.tensor([batch_size, curr_size, poly_size]))
		cse_var_105 = unary(Llist(abs_elem.network, [1]*(cse_var_102), None, None,torch.nonzero(abs_elem.d['llist']).flatten().tolist()).get_metadata('layer', batch_size), operator.neg)
		cse_var_104 = Llist(abs_elem.network, [1]*(cse_var_102), None, None,torch.nonzero(abs_elem.d['llist']).flatten().tolist())
		cse_var_106 = abs_elem.get_elem('L', cse_var_104)
		cse_var_107 = abs_elem.get_elem('U', cse_var_104)
		cse_var_109 = cse_var_107.get_const()
		cse_var_108 = cse_var_107.get_mat(abs_elem)
		cse_var_111 = cse_var_106.get_const()
		cse_var_110 = cse_var_106.get_mat(abs_elem)
		import threading
		l_new = None
		u_new = None
		def _par_thread_1():
			nonlocal l_new
			vertices_stop1 = False
			phi_trav_exp1_1_1 = cse_var_41
			while(True):
				cse_var_24 = phi_trav_exp1_1_1.get_mat(abs_elem)
				vertices1_1_1 = binary(cse_var_24, cse_var_10, operator.ne)
				vertices_stop_default1 = get_default_stop([batch_size, curr_size, poly_size], abs_elem, batch_size, curr_size, poly_size)
				vertices_stop_temp1 = binary(SparseTensor([], [], 0, torch.tensor([]), dense_const=vertices_stop1, type= type(vertices_stop1)).unsqueeze(0).unsqueeze(1).unsqueeze(2).repeat(torch.tensor([batch_size, curr_size, poly_size])), vertices_stop_default1, operator.or_)
				vertices1_1_2 = binary(vertices1_1_1, unary(vertices_stop_temp1, operator.not_), operator.and_)
				if(unary(any(vertices1_1_2), operator.not_)):
					break
				priority_vertices1 = get_max_priority(cse_var_105, vertices1_1_2)
				vertices_final_stop1 = binary(vertices_stop_temp1, repeat(unary(priority_vertices1, operator.not_), torch.tensor([batch_size, curr_size, 1])), operator.or_)
				polyexp_stop1 = filter_trav_exp_stop(phi_trav_exp1_1_1, vertices_final_stop1)
				polyexp_not_stop1 = filter_trav_exp_not_stop(phi_trav_exp1_1_1, vertices_final_stop1)
				cse_var_98 = polyexp_not_stop1.get_mat(abs_elem)
				cse_var_95 = cse_var_98.unsqueeze(3)
				cse_var_90 = clamp(cse_var_98, False, 0)
				cse_var_92 = clamp(cse_var_98, True, 0)
				cse_var_86 = clamp(cse_var_95, False, 0)
				cse_var_88 = clamp(cse_var_95, True, 0)
				cse_var_56 = binary(inner_prod(cse_var_92, cse_var_111.squeeze(1)), inner_prod(cse_var_90, cse_var_109.squeeze(1)), operator.add)
				cse_var_57 = binary(inner_prod(cse_var_88.squeeze(3), cse_var_110.squeeze(1)), inner_prod(cse_var_86.squeeze(3), cse_var_108.squeeze(1)), operator.add)
				cse_var_55 = binary(cse_var_56, polyexp_not_stop1.get_const(), operator.add)
				trav_exp1_4_3 = PolyExpSparse(abs_elem.network, binary(cse_var_57, polyexp_stop1.get_mat(abs_elem), operator.add) , binary(cse_var_55, polyexp_stop1.get_const(), operator.add))
				phi_trav_exp1_1_1 = trav_exp1_4_3
			cse_var_22 = Llist(abs_elem.network, [1]*(phi_trav_exp1_1_1.mat.dims-1), None, None,torch.nonzero(abs_elem.d['llist']).flatten().tolist())
			cse_var_99 = phi_trav_exp1_1_1.get_mat(abs_elem)
			l_new = binary(binary(inner_prod(clamp(cse_var_99, True, 0), abs_elem.get_elem('l', cse_var_22).squeeze(1)), inner_prod(clamp(cse_var_99, False, 0), abs_elem.get_elem('u', cse_var_22).squeeze(1)), operator.add), phi_trav_exp1_1_1.get_const(), operator.add)
		def _par_thread_2():
			nonlocal u_new
			vertices_stop2 = False
			phi_trav_exp2_5_1 = cse_var_41
			while(True):
				cse_var_11 = phi_trav_exp2_5_1.get_mat(abs_elem)
				vertices2_5_1 = binary(cse_var_11, cse_var_10, operator.ne)
				vertices_stop_default2 = get_default_stop([batch_size, curr_size, poly_size], abs_elem, batch_size, curr_size, poly_size)
				vertices_stop_temp2 = binary(SparseTensor([], [], 0, torch.tensor([]), dense_const=vertices_stop2, type= type(vertices_stop2)).unsqueeze(0).unsqueeze(1).unsqueeze(2).repeat(torch.tensor([batch_size, curr_size, poly_size])), vertices_stop_default2, operator.or_)
				vertices2_5_2 = binary(vertices2_5_1, unary(vertices_stop_temp2, operator.not_), operator.and_)
				if(unary(any(vertices2_5_2), operator.not_)):
					break
				priority_vertices2 = get_max_priority(cse_var_105, vertices2_5_2)
				vertices_final_stop2 = binary(vertices_stop_temp2, repeat(unary(priority_vertices2, operator.not_), torch.tensor([batch_size, curr_size, 1])), operator.or_)
				polyexp_stop2 = filter_trav_exp_stop(phi_trav_exp2_5_1, vertices_final_stop2)
				polyexp_not_stop2 = filter_trav_exp_not_stop(phi_trav_exp2_5_1, vertices_final_stop2)
				cse_var_83 = polyexp_not_stop2.get_mat(abs_elem)
				cse_var_80 = cse_var_83.unsqueeze(3)
				cse_var_75 = clamp(cse_var_83, False, 0)
				cse_var_77 = clamp(cse_var_83, True, 0)
				cse_var_71 = clamp(cse_var_80, False, 0)
				cse_var_73 = clamp(cse_var_80, True, 0)
				cse_var_47 = binary(inner_prod(cse_var_77, cse_var_109.squeeze(1)), inner_prod(cse_var_75, cse_var_111.squeeze(1)), operator.add)
				cse_var_48 = binary(inner_prod(cse_var_73.squeeze(3), cse_var_108.squeeze(1)), inner_prod(cse_var_71.squeeze(3), cse_var_110.squeeze(1)), operator.add)
				cse_var_46 = binary(cse_var_47, polyexp_not_stop2.get_const(), operator.add)
				trav_exp2_8_3 = PolyExpSparse(abs_elem.network, binary(cse_var_48, polyexp_stop2.get_mat(abs_elem), operator.add) , binary(cse_var_46, polyexp_stop2.get_const(), operator.add))
				phi_trav_exp2_5_1 = trav_exp2_8_3
			cse_var_8 = Llist(abs_elem.network, [1]*(phi_trav_exp2_5_1.mat.dims-1), None, None,torch.nonzero(abs_elem.d['llist']).flatten().tolist())
			cse_var_84 = phi_trav_exp2_5_1.get_mat(abs_elem)
			u_new = binary(binary(inner_prod(clamp(cse_var_84, True, 0), abs_elem.get_elem('u', cse_var_8).squeeze(1)), inner_prod(clamp(cse_var_84, False, 0), abs_elem.get_elem('l', cse_var_8).squeeze(1)), operator.add), phi_trav_exp2_5_1.get_const(), operator.add)
		_par_n_orig = torch.get_num_threads()
		_par_n_cores = torch.multiprocessing.cpu_count()
		torch.set_num_threads(max(1, min(_par_n_orig, _par_n_cores // 2)))
		_t1 = threading.Thread(target=_par_thread_1)
		_t2 = threading.Thread(target=_par_thread_2)
		_t1.start(); _t2.start()
		_t1.join(); _t2.join()
		torch.set_num_threads(_par_n_orig)
		return l_new, u_new, cse_var_41, cse_var_41
	
	def Relu(self, abs_elem, prev, curr, poly_size, curr_size, prev_size, input_size, batch_size):
		cse_var_38 = abs_elem.get_elem('l', prev)
		cse_var_39 = SparseTensor([], [], 0, torch.tensor([]), dense_const=0.0, type= type(0.0)).unsqueeze(0).unsqueeze(1).repeat(torch.tensor([batch_size, curr_size]))
		cse_var_43 = binary(cse_var_38, cse_var_39, operator.ge)
		rewrite_new_0 = convert_to_float(cse_var_43)
		cse_var_101 = SparseTensor([], [], 0, torch.tensor([]), dense_const=1.0, type= type(1.0)).unsqueeze(0).unsqueeze(1).repeat(torch.tensor([batch_size, curr_size]))
		l_new = binary(binary(rewrite_new_0, cse_var_38, operator.mul), binary(binary(cse_var_101, rewrite_new_0, operator.sub), cse_var_39, operator.mul), operator.add)
		cse_var_37 = abs_elem.get_elem('u', prev)
		rewrite_new_1 = convert_to_float(binary(cse_var_37, cse_var_39, operator.ge))
		u_new = binary(binary(rewrite_new_1, cse_var_37, operator.mul), binary(binary(cse_var_101, rewrite_new_1, operator.sub), cse_var_39, operator.mul), operator.add)
		cse_var_35 = prev.convert_to_poly(abs_elem)
		cse_var_44 = repeat(cse_var_35.get_const(), torch.tensor([batch_size, 1]))
		cse_var_45 = repeat(cse_var_35.get_mat(abs_elem), torch.tensor([batch_size, 1, 1]))
		cse_var_34 = PolyExpSparse(abs_elem.network, 0.0, 0.0)
		cse_var_36 = binary(binary(cse_var_38, cse_var_37, operator.add), cse_var_39, operator.ge)
		cse_var_100 = convert_to_float(cse_var_36)
		rewrite_new_2 = repeat(cse_var_100.unsqueeze(2), torch.tensor([1, 1, poly_size]))
		cse_var_103 = binary(cse_var_101, cse_var_100, operator.sub)
		L_new = PolyExpSparse(abs_elem.network, binary(binary(rewrite_new_2, cse_var_45, operator.mul), repeat(binary(cse_var_103, SparseTensor([], [], 0, torch.tensor([]), dense_const=cse_var_34.get_mat(abs_elem), type= type(cse_var_34.get_mat(abs_elem))).unsqueeze(0).unsqueeze(1).repeat(torch.tensor([batch_size, curr_size])), operator.mul).unsqueeze(2), torch.tensor([1, 1, poly_size])), operator.add) , binary(binary(cse_var_100, cse_var_44, operator.mul), binary(cse_var_103, SparseTensor([], [], 0, torch.tensor([]), dense_const=cse_var_34.get_const(), type= type(cse_var_34.get_const())).unsqueeze(0).unsqueeze(1).repeat(torch.tensor([batch_size, curr_size])), operator.mul), operator.add))
		cse_var_31 = binary(cse_var_37, cse_var_38, operator.sub)
		cse_var_33 = binary(cse_var_37, cse_var_31, operator.truediv)
		cse_var_68 = binary(cse_var_33, cse_var_44, operator.mul)
		cse_var_69 = binary(repeat(cse_var_33.unsqueeze(2), torch.tensor([1, 1, poly_size])), cse_var_45, operator.mul)
		cse_var_67 = binary(cse_var_68, binary(binary(cse_var_37, cse_var_38, operator.mul), cse_var_31, operator.truediv), operator.sub)
		cse_var_29 = PolyExpSparse(abs_elem.network, 0.0, cse_var_39)
		cse_var_30 = binary(cse_var_37, cse_var_39, operator.le)
		cse_var_65 = where(cse_var_30, cse_var_29.get_const(), cse_var_67)
		cse_var_66 = where(repeat(cse_var_30.unsqueeze(2), torch.tensor([1, 1, poly_size])), cse_var_29.get_mat(abs_elem), cse_var_69)
		U_new = PolyExpSparse(abs_elem.network, where(repeat(cse_var_43.unsqueeze(2), torch.tensor([1, 1, poly_size])), cse_var_45, cse_var_66) , where(cse_var_43, cse_var_44, cse_var_65))
		return l_new, u_new, L_new, U_new
	
